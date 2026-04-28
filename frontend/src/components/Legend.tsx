import React from 'react'

// Du haut (dangereux) vers le bas (négligeable) — couleurs synchronisées avec DB_LEVEL_COLOR_STOPS
const BLOCKS = [
  { sublabel: 'Dangereux',   range: '(≥ 80 dB)' },
  { sublabel: 'Gênant',      range: '(≥ 70 dB)' },
  { sublabel: 'Perceptible', range: '(> 60 dB)' },
  { sublabel: 'Négligeable', range: '(51-60 dB)' },
]

const BLOCK_HEIGHT = 28 // px — 4 blocs = 112px total
const TOTAL_HEIGHT = BLOCK_HEIGHT * BLOCKS.length
const GRADIENT = 'linear-gradient(to bottom, #dc2626, #f97316 33%, #eab308 66%, #22c55e 100%)'

export default React.memo(function Legend() {
  return (
    <div className="bg-slate-900/95 border border-slate-700 rounded-xl p-4 shadow-2xl">
      <h3 className="text-sky-400 font-semibold text-sm mb-3">Niveau de bruit</h3>
      <div className="flex items-stretch gap-2.5">
        {/* Barre de dégradé continue, divisée en 4 blocs égaux par des séparateurs */}
        <div className="relative w-7 flex-shrink-0 rounded-sm overflow-hidden" style={{ height: TOTAL_HEIGHT }}>
          <div className="absolute inset-0" style={{ background: GRADIENT }} />
          {[1, 2, 3].map(i => (
            <div
              key={i}
              className="absolute left-0 right-0 h-px bg-black"
              style={{ top: `${i * 25}%` }}
            />
          ))}
        </div>
        {/* Labels : un par bloc, centré verticalement dans son bloc */}
        <div className="flex flex-col" style={{ height: TOTAL_HEIGHT }}>
          {BLOCKS.map(({ sublabel, range }) => (
            <div key={sublabel} className="flex items-center flex-1 gap-1">
              <span className="text-slate-200 text-xs font-semibold whitespace-nowrap">{sublabel}</span>
              <span className="text-slate-400 text-xs whitespace-nowrap">{range}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
})
