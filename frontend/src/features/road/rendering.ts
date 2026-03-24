import type { MapRef } from 'react-map-gl/maplibre'
import type { RoadSegment } from '../../hooks/useRoadData'
import { ROAD_WIDTH_BY_VOIES, ROAD_BASE_WIDTH_PX, CORRIDOR_N_PASSES, LAT_REF_ROAD } from './constants'
import { getRoadColor, calcCorridorHalfWidthPx, hexToRgb, interpolateColor } from './utils'

const MIN_PX_SQ = 4 // skip points < 2px de distance depuis le dernier dessiné
const GREEN_51DB = '#22c55e' // couleur bord de halo (bruit minimal)

interface SegProjected {
  color: string
  halfWidthPx: number
  points: { x: number; y: number }[]
}

export interface RoadStyleCache {
  colors: Map<string, { color: string; lineWidth: number }>
}

/**
 * Pré-calcule les couleurs et largeurs de trait pour chaque segment.
 * À appeler une seule fois quand roadData change.
 */
export function precomputeRoadStyles(segments: RoadSegment[]): RoadStyleCache {
  const colors = new Map<string, { color: string; lineWidth: number }>()
  for (const seg of segments) {
    const color = getRoadColor(seg.noise_db)
    const lineWidth = ROAD_WIDTH_BY_VOIES[Math.min(seg.nb_voies || 1, 3)] ?? ROAD_BASE_WIDTH_PX
    colors.set(seg.code_pme, { color, lineWidth })
  }
  return { colors }
}

/**
 * Dessine les segments routiers avec un halo dégradé (style corridors avion).
 * Multi-passes : extérieur (vert transparent) → centre (couleur bruit opaque).
 * @param ctx - Contexte canvas 2D
 * @param segments - Liste des segments routiers avec niveaux de bruit
 * @param map - Référence à la carte MapGL pour la projection
 * @param zoom - Niveau de zoom courant
 * @param styleCache - Cache de styles pré-calculé (optionnel, recalcule si absent)
 */
export function drawRoadSegments(
  ctx: CanvasRenderingContext2D,
  segments: RoadSegment[],
  map: MapRef,
  zoom: number,
  styleCache?: RoadStyleCache,
): void {
  const pixelRatio = window.devicePixelRatio || 1
  const canvas = ctx.canvas

  const cssWidth = canvas.offsetWidth
  const cssHeight = canvas.offsetHeight
  if (cssWidth > 0 && cssHeight > 0 && (canvas.width !== cssWidth * pixelRatio || canvas.height !== cssHeight * pixelRatio)) {
    canvas.width = cssWidth * pixelRatio
    canvas.height = cssHeight * pixelRatio
  }
  ctx.clearRect(0, 0, canvas.width, canvas.height)
  ctx.save()
  ctx.scale(pixelRatio, pixelRatio)

  ctx.lineCap = 'round'
  ctx.lineJoin = 'round'

  // Même formule que aircraft/rendering.ts
  const metersPerPixel = (156543.03 * Math.cos(LAT_REF_ROAD * Math.PI / 180)) / Math.pow(2, zoom)

  // Viewport culling
  const bounds = (map as any).getBounds()
  const west = bounds.getWest()
  const east = bounds.getEast()
  const south = bounds.getSouth()
  const north = bounds.getNorth()

  // Filtrer les segments visibles et pré-projeter les coordonnées (1× par point)
  const projected: SegProjected[] = []
  for (const seg of segments) {
    const minLat = Math.min(seg.lat_deb, seg.lat_fin)
    const maxLat = Math.max(seg.lat_deb, seg.lat_fin)
    const minLon = Math.min(seg.lon_deb, seg.lon_fin)
    const maxLon = Math.max(seg.lon_deb, seg.lon_fin)
    if (maxLat < south || minLat > north || maxLon < west || minLon > east) continue

    const color = styleCache?.colors.get(seg.code_pme)?.color ?? getRoadColor(seg.noise_db)
    const halfWidthPx = calcCorridorHalfWidthPx(seg.noise_db, metersPerPixel)

    const points: { x: number; y: number }[] = []
    if (seg.geom_osm && seg.geom_osm.length >= 2) {
      let prevX = NaN, prevY = NaN
      for (const [lat, lon] of seg.geom_osm) {
        const p = map.project([lon, lat])
        const dx = p.x - prevX, dy = p.y - prevY
        if (points.length > 0 && dx * dx + dy * dy < MIN_PX_SQ) continue
        points.push({ x: p.x, y: p.y })
        prevX = p.x; prevY = p.y
      }
    } else {
      const a = map.project([seg.lon_deb, seg.lat_deb])
      const b = map.project([seg.lon_fin, seg.lat_fin])
      points.push({ x: a.x, y: a.y }, { x: b.x, y: b.y })
    }
    if (points.length < 2) continue

    projected.push({ color, halfWidthPx, points })
  }

  // Helper : dessine le path d'un segment pré-projeté
  function addSegPath(pts: { x: number; y: number }[]) {
    ctx.moveTo(pts[0].x, pts[0].y)
    for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i].x, pts[i].y)
  }

  // Zoom faible ou pan en cours : une ligne fine par segment, pas de halo
  if (zoom < 8) {
    const groups = new Map<string, SegProjected[]>()
    for (const item of projected) {
      if (!groups.has(item.color)) groups.set(item.color, [])
      groups.get(item.color)!.push(item)
    }
    ctx.globalAlpha = 0.8
    ctx.lineWidth = 1
    for (const [color, items] of groups) {
      ctx.strokeStyle = color
      ctx.beginPath()
      for (const { points } of items) addSegPath(points)
      ctx.stroke()
    }
    ctx.globalAlpha = 1
    ctx.restore()
    return
  }

  // Multi-passes halo : N → 1 (extérieur → intérieur)
  const innerFraction = 1 / CORRIDOR_N_PASSES  // fraction de la passe la plus intérieure
  for (let pass = CORRIDOR_N_PASSES; pass >= 1; pass--) {
    const fraction = pass / CORRIDOR_N_PASSES  // 1.0 (outer) → 0.2 (inner)
    // bord=0, centre=0.55 — même courbe que les halos avions
    const alpha = 0.55 * Math.pow(1 - fraction, 1.5)

    // Grouper par (color|lineWidthBucket) pour minimiser les stroke()
    const groups = new Map<string, { color: string; lineWidth: number; items: SegProjected[] }>()
    for (const item of projected) {
      const lineWidth = 2 * item.halfWidthPx * fraction
      if (lineWidth < 0.5) continue
      // Couleur interpolée linéaire : outer=vert, inner=couleur bruit exacte
      const t = (1 - fraction) / (1 - innerFraction)
      const blendColor = interpolateColor(GREEN_51DB, item.color, t)
      const bucket = Math.round(lineWidth * 2) / 2  // arrondi à 0.5px
      const key = `${blendColor}|${bucket}`
      if (!groups.has(key)) groups.set(key, { color: blendColor, lineWidth: bucket, items: [] })
      groups.get(key)!.items.push(item)
    }

    ctx.globalAlpha = alpha
    for (const { color, lineWidth, items } of groups.values()) {
      ctx.strokeStyle = color
      ctx.lineWidth = lineWidth
      ctx.beginPath()
      for (const { points } of items) addSegPath(points)
      ctx.stroke()
    }
  }

  ctx.globalAlpha = 1
  ctx.restore()
}
