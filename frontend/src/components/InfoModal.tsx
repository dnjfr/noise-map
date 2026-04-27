import React from 'react'

interface Props {
  onClose: () => void
}

export default function InfoModal({ onClose }: Props) {
  return (
    <div className="absolute inset-0 z-[3000] flex items-center justify-center">
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={onClose} />
      <div className="relative z-10 bg-slate-900/95 border border-slate-700 rounded-xl shadow-2xl p-6 max-w-sm w-full mx-4">
        <button
          onClick={onClose}
          className="absolute top-3 right-3 text-slate-500 hover:text-white transition-colors cursor-pointer"
          aria-label="Fermer"
        >
          <svg viewBox="0 0 24 24" className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>

        <h2 className="text-white font-semibold text-base mb-0.5">Carte du bruit en France</h2>
        <p className="text-slate-500 text-xs mb-4">Données semi temps réel</p>

        <p className="text-slate-300 text-sm mb-3">
          Visualisation en quasi temps réel des niveaux de bruit aérien, routier et ferroviaire en France,
          à partir de sources de données publiques.
        </p>

        <p className="text-slate-400 text-sm mb-4">
          Les cartes de bruit existantes reposent sur des snapshots statiques issus de comptages périodiques.
          Ce projet propose une alternative dynamique, mise à jour en continu.
        </p>

        <div className="mb-4">
          <h3 className="text-slate-200 text-sm font-medium mb-2">Sources de données</h3>
          <ul className="space-y-1.5 text-sm">
            <li className="text-slate-400"><span className="text-blue-400 font-medium">Aérien</span> - positions ADS-B via adsb.one</li>
            <li className="text-slate-400"><span className="text-orange-400 font-medium">Routier</span> - trafic autoroutier via TomTom</li>
            <li className="text-slate-400"><span className="text-green-400 font-medium">Ferroviaire</span> - GTFS-RT SNCF</li>
          </ul>
        </div>

        <div className="mb-5">
          <h3 className="text-slate-200 text-sm font-medium mb-2">Stack technique</h3>
          <div className="flex flex-wrap gap-1.5">
            {['Kafka', 'TimescaleDB', 'FastAPI', 'Vite', 'MapLibre', 'pfaedle'].map(t => (
              <span key={t} className="px-2 py-0.5 bg-slate-800 border border-slate-700 rounded text-xs text-slate-300">{t}</span>
            ))}
          </div>
        </div>

        <a
          href="https://github.com/dnjfr/noise-map"
          target="_blank"
          rel="noopener noreferrer"
          className="text-blue-400 text-sm hover:text-blue-300 transition-colors"
        >
          Voir le code source →
        </a>
      </div>
    </div>
  )
}
