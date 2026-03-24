const EARTH_RADIUS = 6371000 // metres

function haversineDistance(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const dLat = (lat2 - lat1) * Math.PI / 180
  const dLon = (lon2 - lon1) * Math.PI / 180
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) * Math.sin(dLon / 2) ** 2
  return EARTH_RADIUS * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a))
}

function bearing(from: [number, number], to: [number, number]): number {
  const lat1 = from[0] * Math.PI / 180
  const lat2 = to[0] * Math.PI / 180
  const dLon = (to[1] - from[1]) * Math.PI / 180
  const y = Math.sin(dLon) * Math.cos(lat2)
  const x = Math.cos(lat1) * Math.sin(lat2) - Math.sin(lat1) * Math.cos(lat2) * Math.cos(dLon)
  return ((Math.atan2(y, x) * 180 / Math.PI) + 360) % 360
}

/**
 * Recherche binaire : trouve l'index du segment contenant `dist`.
 * Retourne i tel que shape[i][2] <= dist < shape[i+1][2].
 * shape_dist_traveled (index [2]) doit être trié croissant.
 */
function findSegment(shape: [number, number, number][], dist: number): number {
  let lo = 0
  let hi = shape.length - 2
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1
    if (shape[mid][2] <= dist) {
      lo = mid
    } else {
      hi = mid - 1
    }
  }
  return lo
}

/** Longueur totale d'une polyline en mètres */
export function polylineLength(line: [number, number, number][]): number {
  if (line.length === 0) return 0
  return line[line.length - 1][2] - line[0][2]
}

/**
 * Projette un point sur une polyline.
 * Retourne le shape_dist_traveled interpolé entre les deux extrémités du segment le plus proche.
 * Utilise une projection planaire corrigée par cos(lat) pour les coordonnées non-isométriques.
 * Note : reste en O(n) car on cherche le segment le plus proche géographiquement.
 */
export function projectOnPolyline(shape: [number, number, number][], pos: [number, number]): number {
  if (shape.length === 0) return 0
  if (shape.length === 1) return shape[0][2]

  let minDist = Infinity
  let bestShapeDist = shape[0][2]

  for (let i = 0; i < shape.length - 1; i++) {
    const [lat1, lon1, dist1] = shape[i]
    const [lat2, lon2, dist2] = shape[i + 1]

    // Projection planaire corrigée par cos(lat) — valide pour des segments courts
    const cosLat = Math.cos(lat1 * Math.PI / 180)
    const dLat = lat2 - lat1
    const dLon = (lon2 - lon1) * cosLat
    const pLat = pos[0] - lat1
    const pLon = (pos[1] - lon1) * cosLat
    const seg2 = dLat * dLat + dLon * dLon
    const t = seg2 > 0 ? Math.max(0, Math.min(1, (pLat * dLat + pLon * dLon) / seg2)) : 0

    const projLat = lat1 + t * (lat2 - lat1)
    const projLon = lon1 + t * (lon2 - lon1)
    const d = haversineDistance(pos[0], pos[1], projLat, projLon)

    if (d < minDist) {
      minDist = d
      bestShapeDist = dist1 + t * (dist2 - dist1)
    }
  }

  return bestShapeDist
}

/**
 * Retourne le point [lat, lng] à une distance donnée (en unités shape_dist_traveled).
 * Recherche binaire O(log n) au lieu de linéaire O(n).
 */
export function posAtDist(shape: [number, number, number][], dist: number): [number, number] {
  if (shape.length === 0) return [0, 0]
  if (shape.length === 1) return [shape[0][0], shape[0][1]]
  if (dist <= shape[0][2]) return [shape[0][0], shape[0][1]]
  if (dist >= shape[shape.length - 1][2]) return [shape[shape.length - 1][0], shape[shape.length - 1][1]]

  const i = findSegment(shape, dist)
  const da = shape[i][2]
  const db = shape[i + 1][2]
  const span = db - da
  const t = span > 0 ? (dist - da) / span : 0
  const lat = shape[i][0] + t * (shape[i + 1][0] - shape[i][0])
  const lng = shape[i][1] + t * (shape[i + 1][1] - shape[i][1])
  return [lat, lng]
}

/**
 * Retourne le cap (bearing en degrés) de la voie à une distance donnée.
 * Recherche binaire O(log n) au lieu de linéaire O(n).
 */
export function headingAtDist(shape: [number, number, number][], dist: number): number {
  if (shape.length < 2) return 0
  if (dist >= shape[shape.length - 1][2]) {
    return bearing(
      [shape[shape.length - 2][0], shape[shape.length - 2][1]],
      [shape[shape.length - 1][0], shape[shape.length - 1][1]]
    )
  }

  const i = findSegment(shape, dist)
  return bearing([shape[i][0], shape[i][1]], [shape[i + 1][0], shape[i + 1][1]])
}
