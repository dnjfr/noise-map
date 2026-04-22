import React from 'react'
import type { MapStyleKey } from './Map'
import { MAP_STYLES } from './Map'
import mapDark from '../assets/icons/map_dark.png'
import mapGrey from '../assets/icons/map_grey.png'
import mapLight from '../assets/icons/map_light.png'

interface Props {
  currentStyle: MapStyleKey
  onStyleChange: (style: MapStyleKey) => void
}

/** Sélecteur de style de fond de carte — n'affiche que les styles configurés dans l'env. */
const ALL_STYLES: { key: MapStyleKey; label: string; icon: string; border: string; activeBorder: string }[] = [
  {
    key: 'dark',
    label: 'Sombre',
    icon: mapDark,
    border: 'border-slate-600',
    activeBorder: 'border-blue-400',
  },
  {
    key: 'default',
    label: 'Standard',
    icon: mapGrey,
    border: 'border-slate-400',
    activeBorder: 'border-blue-400',
  },
  {
    key: 'light',
    label: 'Clair',
    icon: mapLight,
    border: 'border-slate-300',
    activeBorder: 'border-blue-400',
  },
]

const STYLES = ALL_STYLES.filter(s => s.key in MAP_STYLES)

export default React.memo(function MapStyleToggle({ currentStyle, onStyleChange }: Props) {
  return (
    <div className="flex flex-col-reverse" style={{ gap: 15 }}>
      {STYLES.map((style) => {
        const isActive = currentStyle === style.key
        return (
          <button
            key={style.key}
            title={style.label}
            onClick={() => onStyleChange(style.key)}
            className={[
              'w-9 h-9 rounded-lg shadow-2xl border-2 transition-all duration-200 cursor-pointer overflow-hidden p-0',
              isActive ? `${style.activeBorder} scale-110` : `${style.border} opacity-80 hover:opacity-100 hover:scale-105`,
            ].join(' ')}
          >
            <img
              src={style.icon}
              alt={style.label}
              className="w-full h-full object-cover rounded-md"
              draggable={false}
            />
          </button>
        )
      })}
    </div>
  )
})
