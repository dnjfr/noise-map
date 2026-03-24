export const NOISE_REFERENCE_DB_BY_CATEGORY: Record<string, number> = {
  A1: 65, A2: 72, A3: 80, A4: 82, A5: 85,
}

export const ICON_MIN = 6
export const MAX_SIZE_BY_CATEGORY: Record<string, number> = {
  A1: 13, A2: 16, A3: 19, A4: 22, A5: 25,
}
export const DEFAULT_MAX_SIZE = 17

export const DB_LEVEL_COLOR_STOPS: Array<[number, string]> = [
  [51, '#22c55e'],
  [60, '#eab308'],
  [70, '#f97316'],
  [80, '#dc2626'],
]

export const ANIMATION_DURATION = 3200
export const EARTH_RADIUS = 6371000
export const FRAME_INTERVAL = 1000 / 30

export interface AnimData {
  fromLat: number; fromLng: number
  toLat: number; toLng: number
  startTime: number
}
