import React from 'react'

interface Props {
  showAircraft: boolean
  showRoads: boolean
  showRailways: boolean
  onToggleAircraft: () => void
  onToggleRoads: () => void
  onToggleRailways: () => void
}

/** Barre de 3 checkboxes pour activer/désactiver les couches Avions, Routes et Trains. */
export default React.memo(function LayerToggle({ showAircraft, showRoads, showRailways, onToggleAircraft, onToggleRoads, onToggleRailways }: Props) {
  return (
    <div className="flex gap-2">
      <label className="flex items-center gap-2 cursor-pointer bg-slate-900/95 border border-slate-700 rounded-xl px-3 py-2 shadow-2xl select-none">
        <input
          type="checkbox"
          checked={showAircraft}
          onChange={onToggleAircraft}
          className="accent-blue-400 w-4 h-4"
        />
        <span className="text-slate-200 text-sm font-medium">✈ Avions</span>
      </label>
      <label className="flex items-center gap-2 cursor-pointer bg-slate-900/95 border border-slate-700 rounded-xl px-3 py-2 shadow-2xl select-none">
        <input
          type="checkbox"
          checked={showRoads}
          onChange={onToggleRoads}
          className="accent-blue-400 w-4 h-4"
        />
        <span className="flex items-center gap-1.5 text-slate-200 text-sm font-medium">
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="w-4 h-4 shrink-0">
            <path d="M4 3h2v18H4V3zm14 0h2v18h-2V3zm-5 3h2v3h-2V6zm0 6h2v3h-2v-3zm0 6h2v3h-2v-3z"/>
          </svg>
          Routes
        </span>
      </label>
      <label className="flex items-center gap-2 cursor-pointer bg-slate-900/95 border border-slate-700 rounded-xl px-3 py-2 shadow-2xl select-none">
        <input
          type="checkbox"
          checked={showRailways}
          onChange={onToggleRailways}
          className="accent-blue-400 w-4 h-4"
        />
        <span className="flex items-center gap-1.5 text-slate-200 text-sm font-medium">
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="w-4 h-4 shrink-0">
            <path d="M12 2C8.13 2 5 3.79 5 6v8.5C5 16.43 6.57 18 8.5 18h.17L7 19.65V20h2l1.33-2h3.33L15 20h2v-.35L15.33 18H15.5C17.43 18 19 16.43 19 14.5V6C19 3.79 15.87 2 12 2zM9 15c-.55 0-1-.45-1-1s.45-1 1-1 1 .45 1 1-.45 1-1 1zm6 0c-.55 0-1-.45-1-1s.45-1 1-1 1 .45 1 1-.45 1-1 1zM17 9H7V6h10v3z"/>
          </svg>
          Trains
        </span>
      </label>
    </div>
  )
})
