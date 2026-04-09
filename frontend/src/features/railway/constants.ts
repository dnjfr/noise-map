export const RAILWAY_LINE_COLOR = '#c4bebe'
export const RAILWAY_LINE_WIDTH = 1.5
export const RAILWAY_LINE_OPACITY = 0.9

export const TRAIN_ICON_SIZE = 14
export const TRAIN_COLOR = '#a5b4fc'

/** Niveaux de référence bruit par type de service SNCF (dB(A) à 25m) */
export const RAILWAY_NOISE_REF: Record<string, { lRef: number; vRef: number }> = {
  TGV:  { lRef: 92, vRef: 300 },
  IC:   { lRef: 82, vRef: 200 },
  TER:  { lRef: 80, vRef: 140 },
  FRET: { lRef: 88, vRef: 100 },
}
export const DEFAULT_RAILWAY_NOISE_REF = { lRef: 80, vRef: 140 }
export const TRAIN_SLIDE_DURATION = 2000  // 2s de transition douce

export interface TrainAnimData {
  distFrom: number    // distance sur la shape au moment de la mise à jour (position interpolée)
  distTarget: number  // distance projetée depuis la position API (cible du slide)
  speedMs: number     // vitesse en m/s
  startTime: number   // performance.now()
  maxDist: number     // shape[-1][2] — borne max absolue (Infinity si pas de shape)
  minDist: number     // shape[0][2]  — borne min absolue
  baseLat: number     // lat de référence pour le fallback heading+speed
  baseLng: number     // lng de référence pour le fallback heading+speed
}
