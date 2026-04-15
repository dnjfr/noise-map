import type { LayerProps } from 'react-map-gl/maplibre'
import { RAILWAY_LINE_WIDTH, RAILWAY_LINE_OPACITY } from './constants'

export function getRailwayLineLayer(color: string): LayerProps {
  return {
    id: 'railway-lines',
    type: 'line',
    paint: {
      'line-color': color,
      'line-width': RAILWAY_LINE_WIDTH,
      'line-opacity': RAILWAY_LINE_OPACITY,
    },
    layout: {
      'line-cap': 'round',
      'line-join': 'round',
    },
  }
}
