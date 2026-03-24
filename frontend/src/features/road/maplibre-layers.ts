import type { LayerProps } from 'react-map-gl/maplibre'

// Conversion mètres → pixels par niveau de zoom.
// Formule : 2^zoom / 107430.7 (Mercator projection à lat ~46.6)
// IMPORTANT : ['zoom'] doit être l'input DIRECT d'interpolate (top-level),
// on ne peut PAS imbriquer ['zoom'] dans ['*']. Cf. mapbox-gl-js#5861.
export const M_TO_PX_FACTORS = [
  [6,  0.000596],  // 64 / 107430.7
  [7,  0.001191],
  [8,  0.002383],
  [9,  0.004766],
  [10, 0.009531],
  [11, 0.019062],
  [12, 0.038124],
  [13, 0.076248],
  [14, 0.152496],  // 16384 / 107430.7
] as const

// Palette bruit — transitions vert→ambre→rouge via teintes olive/sauge
export const NOISE_PALETTE: [number, string][] = [
  [51, '#759285'],  // olive foncé
  [55, '#979D78'],  // vert foncé
  [58, '#A29D82'],  // vert forêt profond
  [60, '#c8960a'],  // ambre doré
  [70, '#c85a00'],  // orange brun
  [80, '#ef4444'],  // rouge
]

export const HALO_LAYOUT = {
  'line-cap': 'round' as const,
  'line-join': 'round' as const,
}

/** Expression line-width valide : zoom top-level, data dans les outputs.
 * maxMeters : cap physique en mètres (propagation acoustique).
 * minPx : largeur minimale — garantit la visibilité à bas zoom (ex: core = 1.5px). */
export function haloWidthExpr(maxMeters: number, capPx: number, minPx = 0): any {
  const widthExpr = ['min', ['get', 'corridor_width_m'], maxMeters]
  return [
    'interpolate', ['exponential', 2], ['zoom'],
    ...M_TO_PX_FACTORS.flatMap(([z, f]) => {
      const px = ['min', capPx, ['*', widthExpr, f]]
      return [z, minPx > 0 ? ['max', minPx, px] : px]
    })
  ]
}

/** Expression couleur avec décalage dB optionnel (simule l'atténuation avec la distance). */
export function noiseColorExpr(offsetDb = 0): any {
  const input = offsetDb === 0
    ? ['get', 'noise_db']
    : ['-', ['get', 'noise_db'], offsetDb]
  return [
    'interpolate', ['linear'], input,
    ...NOISE_PALETTE.flat()
  ]
}

// 4 halos + core — propagation acoustique physique (source ligne = route)
// core (50m)  = niveau source,  inner (250m) = -7dB,  mid (500m) = -10dB,  outer = corridor complet
export const roadHaloOuter: LayerProps = {
  id: 'road-halo-outer',
  type: 'line',
  paint: {
    'line-color': noiseColorExpr(15),
    'line-width': haloWidthExpr(99999, 200),
    'line-opacity': 0.07,
    'line-blur': 2,
  },
  layout: HALO_LAYOUT,
}

export const roadHaloMid: LayerProps = {
  id: 'road-halo-mid',
  type: 'line',
  paint: {
    'line-color': noiseColorExpr(10),
    'line-width': haloWidthExpr(500, 40),
    'line-opacity': 0.13,
    'line-blur': 1,
  },
  layout: HALO_LAYOUT,
}

export const roadHaloInner: LayerProps = {
  id: 'road-halo-inner',
  type: 'line',
  paint: {
    'line-color': noiseColorExpr(7),
    'line-width': haloWidthExpr(250, 20),
    'line-opacity': 0.22,
    'line-blur': 1,
  },
  layout: HALO_LAYOUT,
}

export const roadCoreLayer: LayerProps = {
  id: 'road-core',
  type: 'line',
  paint: {
    'line-color': noiseColorExpr(0),
    // minPx=1.5 : garantit une ligne orange visible même à zoom 6 (sinon ≈0.03px)
    'line-width': haloWidthExpr(50, 6, 1.5),
    'line-opacity': 0.60,
    'line-blur': 0,
  },
  layout: HALO_LAYOUT,
}
