import React, { useCallback, useMemo } from 'react'
import { Marker, Popup } from 'react-map-gl/maplibre'
import type { Train } from '../../hooks/useRailwaysData'
import { TRAIN_COLOR, TRAIN_ICON_SIZE } from './constants'
import { buildRailwayPopupContent } from './utils'

export interface TrainMarkerProps {
  train: Train
  lat: number
  lng: number
  heading: number
  zoomFactor: number
  isOpen: boolean
  onClick: (tripId: string) => void
  onClose: () => void
}

function getTrainSvg(size: number): string {
  // Locomotive vue du dessus — orientée vers le haut (heading=0 → nord)
  return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
    <rect x="7" y="3" width="10" height="18" rx="3" fill="${TRAIN_COLOR}" opacity="0.9" stroke="white" stroke-width="1.2" stroke-opacity="0.7"/>
    <rect x="9" y="4" width="6" height="3" rx="1" fill="white" opacity="0.5"/>
    <line x1="8" y1="10" x2="16" y2="10" stroke="white" stroke-width="0.8" opacity="0.4"/>
    <line x1="8" y1="14" x2="16" y2="14" stroke="white" stroke-width="0.8" opacity="0.4"/>
    <circle cx="9.5" cy="18" r="1.2" fill="white" opacity="0.35"/>
    <circle cx="14.5" cy="18" r="1.2" fill="white" opacity="0.35"/>
  </svg>`
}
 
const TrainMarker = React.memo(function TrainMarker({
  train, lat, lng, heading, zoomFactor, isOpen, onClick, onClose,
}: TrainMarkerProps) {
  const pixelSize = useMemo(() =>
    Math.round(TRAIN_ICON_SIZE * Math.max(0.6, Math.min(1.4, 0.6 + zoomFactor * 0.8))),
  [zoomFactor])

  const svgHtml = useMemo(() => ({ __html: getTrainSvg(pixelSize) }), [pixelSize])

  const style = useMemo(() => ({
    transform: `rotate(${heading}deg)`,
    cursor: 'pointer' as const,
    width: pixelSize,
    height: pixelSize,
  }), [heading, pixelSize])

  const handleClick = useCallback((e: { originalEvent: { stopPropagation(): void } }) => {
    e.originalEvent.stopPropagation()
    onClick(train.trip_id)
  }, [train.trip_id, onClick])

  return (
    <>
      <Marker latitude={lat} longitude={lng} anchor="center" onClick={handleClick}>
        <div style={style} dangerouslySetInnerHTML={svgHtml} />
      </Marker>
      {isOpen && (
        <Popup
          latitude={lat}
          longitude={lng}
          anchor="bottom"
          closeButton={true}
          closeOnClick={false}
          onClose={onClose}
        >
          <div
            style={{ fontSize: 13, lineHeight: 1.6 }}
            dangerouslySetInnerHTML={{ __html: buildRailwayPopupContent(train) }}
          />
        </Popup>
      )}
    </>
  )
})

export default TrainMarker
