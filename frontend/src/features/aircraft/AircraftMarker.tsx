import React, { useCallback, useMemo } from 'react'
import { Marker, Popup } from 'react-map-gl/maplibre'
import type { Aircraft } from '../../hooks/useAircraftsData'
import { DEFAULT_MAX_SIZE, ICON_MIN, MAX_SIZE_BY_CATEGORY } from './constants'
import { buildPopupContent, getAircraftSvg } from './utils'

export interface AircraftMarkerProps {
  icao: string
  lat: number
  lng: number
  aircraft: Aircraft
  zoomFactor: number
  isOpen: boolean
  onClick: (icao: string) => void
  onClose: () => void
}

/**
 * Affiche le marker d'un avion sur la carte avec rotation selon son cap.
 * Mémoïsé pour éviter les re-renders inutiles.
 * @param icao - Identifiant ICAO24 de l'avion
 * @param lat - Latitude du marker
 * @param lng - Longitude du marker
 * @param aircraft - Données de l'avion (heading, catégorie, etc.)
 * @param zoomFactor - Facteur de zoom pour adapter la taille du marker
 * @param isOpen - Indique si la popup d'info est ouverte
 * @param onClick - Callback au clic sur le marker
 * @param onClose - Callback à la fermeture de la popup
 */ 
const AircraftMarker = React.memo(function AircraftMarker({
  icao, lat, lng, aircraft, zoomFactor, isOpen, onClick, onClose,
}: AircraftMarkerProps) {
  const pixelSize = useMemo(() => {
    const maxSize = MAX_SIZE_BY_CATEGORY[aircraft.aircraft_category ?? ''] ?? DEFAULT_MAX_SIZE
    return Math.round(ICON_MIN + zoomFactor * (maxSize - ICON_MIN))
  }, [aircraft.aircraft_category, zoomFactor])

  const svgHtml = useMemo(() => ({ __html: getAircraftSvg(pixelSize) }), [pixelSize])

  const style = useMemo(() => ({
    transform: `rotate(${aircraft.heading ?? 0}deg)`,
    cursor: 'pointer' as const,
    width: pixelSize,
    height: pixelSize,
  }), [aircraft.heading, pixelSize])

  const handleClick = useCallback((e: { originalEvent: { stopPropagation(): void } }) => {
    e.originalEvent.stopPropagation()
    onClick(icao)
  }, [icao, onClick])

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
            dangerouslySetInnerHTML={{ __html: buildPopupContent(aircraft) }}
          />
        </Popup>
      )}
    </>
  )
})

export default AircraftMarker
