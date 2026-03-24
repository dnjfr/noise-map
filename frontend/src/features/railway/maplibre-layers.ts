import type { LayerProps } from 'react-map-gl/maplibre'
import { RAILWAY_LINE_COLOR, RAILWAY_LINE_WIDTH, RAILWAY_LINE_OPACITY, TRAIN_COLOR } from './constants'

export const railwayLineLayer: LayerProps = {
  id: 'railway-lines',
  type: 'line',
  paint: {
    'line-color': RAILWAY_LINE_COLOR,
    'line-width': RAILWAY_LINE_WIDTH,
    'line-opacity': RAILWAY_LINE_OPACITY,
  },
  layout: {
    'line-cap': 'round',
    'line-join': 'round',
  },
}
