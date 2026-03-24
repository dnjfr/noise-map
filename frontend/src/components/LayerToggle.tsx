import React from 'react'

interface Props {
  showAircraft: boolean
  showRoads: boolean
  showRailways: boolean
  onToggleAircraft: () => void
  onToggleRoads: () => void
  onToggleRailways: () => void
}

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
        <span className="text-slate-200 text-sm font-medium">⬛ Routes</span>
      </label>
      <label className="flex items-center gap-2 cursor-pointer bg-slate-900/95 border border-slate-700 rounded-xl px-3 py-2 shadow-2xl select-none">
        <input
          type="checkbox"
          checked={showRailways}
          onChange={onToggleRailways}
          className="accent-blue-400 w-4 h-4"
        />
        <span className="text-slate-200 text-sm font-medium">🚆 Trains</span>
      </label>
    </div>
  )
})
