export const ROAD_DB_LEVEL_COLOR_STOPS: Array<[number, string]> = [
  [51, '#22c55e'],
  [60, '#eab308'],
  [70, '#f97316'],
  [80, '#dc2626'],
]

export const ROAD_BASE_WIDTH_PX = 1

export const ROAD_WIDTH_BY_VOIES: Record<number, number> = {
  1: 1,
  2: 1.5,
  3: 2,
}

export const CORRIDOR_N_PASSES = 5
export const CORRIDOR_REF_DIST_M = 25      // même référence que propagation NMPB
export const CORRIDOR_MAX_HALF_WIDTH_PX = 25
export const LAT_REF_ROAD = 46.6           // même que aircraft/rendering.ts
