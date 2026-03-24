/** Utilitaire de mesure de performance pour les hooks de données.
 *  À supprimer une fois le diagnostic terminé. */

const T0 = performance.now()

export async function perfFetch(label: string, url: string): Promise<Response> {
  const t = performance.now()
  const sinceOpen = ((t - T0) / 1000).toFixed(2)
  console.log(`%c[PERF] ${label} ⏳ fetch start (T+${sinceOpen}s)`, 'color: #a3a3a3')

  const res = await fetch(url)

  const tNet = performance.now()
  const networkMs = (tNet - t).toFixed(0)
  const contentLength = res.headers.get('content-length')
  const sizeInfo = contentLength ? `${(+contentLength / 1024).toFixed(0)} KB` : 'taille inconnue'
  console.log(`%c[PERF] ${label} 🌐 réseau: ${networkMs}ms (${sizeInfo})`, 'color: #facc15')

  return res
}

export function perfJson<T>(label: string, res: Response): Promise<T> {
  const t = performance.now()
  return res.json().then((data: T) => {
    const parseMs = (performance.now() - t).toFixed(0)
    const jsonSize = JSON.stringify(data).length
    const sizeKB = (jsonSize / 1024).toFixed(0)
    console.log(`%c[PERF] ${label} 📦 JSON.parse: ${parseMs}ms (${sizeKB} KB dé-sérialisé)`, 'color: #fb923c')
    return data
  })
}

export function perfDone(label: string, count: number | string, startTime: number) {
  const totalMs = (performance.now() - startTime).toFixed(0)
  const sinceOpen = ((performance.now() - T0) / 1000).toFixed(2)
  console.log(`%c[PERF] ${label} ✅ ${count} éléments — total: ${totalMs}ms (T+${sinceOpen}s)`, 'color: #4ade80; font-weight: bold')
}
