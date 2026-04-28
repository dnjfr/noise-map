import { useState, useEffect, useMemo, useRef } from 'react'
import type { Aircraft } from '../../hooks/useAircraftsData'
import type { AnimData } from './constants'
import { EARTH_RADIUS } from './constants'

const MAX_ANIM_DISTANCE_M = 10_000 // au-delà de 10 km, téléportation directe

function haversineDistance(lat1: number, lng1: number, lat2: number, lng2: number): number {
  const dLat = (lat2 - lat1) * Math.PI / 180
  const dLng = (lng2 - lng1) * Math.PI / 180
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) * Math.sin(dLng / 2) ** 2
  return EARTH_RADIUS * 2 * Math.asin(Math.sqrt(a))
}

export function useAircraftAnimationEngine(aircraftsData: Aircraft[], showAircrafts: boolean) {
  const positionsRef = useRef<Map<string, [number, number]>>(new Map())
  const aircraftRef = useRef<Map<string, Aircraft>>(new Map())
  const animDataRef = useRef<Map<string, AnimData>>(new Map())
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const canvasCtxRef = useRef<CanvasRenderingContext2D | null>(null)

  const [positions, setPositions] = useState<Map<string, [number, number]>>(new Map())

  useEffect(() => {
    return () => { canvasRef.current?.remove() }
  }, [])

  useEffect(() => {
    if (canvasRef.current) canvasRef.current.style.display = showAircrafts ? 'block' : 'none'
  }, [showAircrafts])

  useEffect(() => {
    const currentIcaos = new Set(aircraftsData.map(a => a.icao24))

    for (const icao of aircraftRef.current.keys()) {
      if (!currentIcaos.has(icao)) {
        aircraftRef.current.delete(icao)
        positionsRef.current.delete(icao)
        animDataRef.current.delete(icao)
      }
    }

    for (const aircraft of aircraftsData) {
      const prev = aircraftRef.current.get(aircraft.icao24)
      aircraftRef.current.set(aircraft.icao24, aircraft)

      if (!positionsRef.current.has(aircraft.icao24)) {
        positionsRef.current.set(aircraft.icao24, [aircraft.latitude, aircraft.longitude])
      }

      if (!prev || prev.latitude !== aircraft.latitude || prev.longitude !== aircraft.longitude) {
        const from = positionsRef.current.get(aircraft.icao24) ?? [aircraft.latitude, aircraft.longitude]
        const dist = haversineDistance(from[0], from[1], aircraft.latitude, aircraft.longitude)

        if (dist > MAX_ANIM_DISTANCE_M) {
          positionsRef.current.set(aircraft.icao24, [aircraft.latitude, aircraft.longitude])
          animDataRef.current.delete(aircraft.icao24)
        } else {
          animDataRef.current.set(aircraft.icao24, {
            fromLat: from[0], fromLng: from[1],
            toLat: aircraft.latitude, toLng: aircraft.longitude,
            startTime: performance.now(),
          })
        }
      }
    }
  }, [aircraftsData])

  const markerList = useMemo(() => Array.from(positions.entries()), [positions])

  function initCanvas(container: HTMLElement, insertAfter: HTMLElement | null) {
    const canvas = document.createElement('canvas')
    canvas.style.cssText = 'position:absolute;top:0;left:0;width:100%;height:100%;pointer-events:none;'
    canvasRef.current = canvas
    canvasCtxRef.current = canvas.getContext('2d')
    if (insertAfter) {
      insertAfter.insertAdjacentElement('afterend', canvas)
    } else {
      container.appendChild(canvas)
    }
  }

  return { aircraftRef, positionsRef, animDataRef, canvasRef, canvasCtxRef, positions, setPositions, markerList, initCanvas }
}
