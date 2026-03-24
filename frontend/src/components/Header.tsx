import React from 'react'

interface Props {
  lastUpdate: Date | null
}

export default React.memo(function Header({ lastUpdate }: Props) {
  const timeStr = lastUpdate
    ? lastUpdate.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
    : null

  return (
    <div className="bg-slate-900/95 border border-slate-700 rounded-xl p-4 shadow-2xl">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h1 className="text-sky-400 font-bold text-lg leading-tight">Carte du bruit</h1>
          <p className="text-slate-500 text-xs mt-0.5">France Métropolitaine</p>
        </div>
        <span className="text-xs bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 rounded-full px-2 py-0.5 flex-shrink-0">
          Live
        </span>
      </div>
      {timeStr && (
        <p className="text-slate-500 text-xs mt-2 tabular-nums">MAJ : {timeStr}</p>
      )}
    </div>
  )
})
