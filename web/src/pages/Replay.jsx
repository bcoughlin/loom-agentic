import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import LoomPlayer from '../components/LoomPlayer'
import { api } from '../lib/api'

/**
 * Replay page — loads a single agent run JSON and hands it to LoomPlayer.
 *
 * Loading strategies, in order of preference (mirrors the static
 * player.html conventions so behavior is consistent across surfaces):
 *   1. ?src=<url>            — fetch run JSON from that URL
 *   2. ?run=<run_id>          — fetch /api/runs/<run_id> from serve.py
 *   3. drag-and-drop a .json file onto the page
 *   4. (no input) — show empty state with instructions
 */
export default function Replay() {
  const [params] = useSearchParams()
  const [run, setRun] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)

  const src = params.get('src')
  const runId = params.get('run')

  useEffect(() => {
    let cancelled = false
    async function load() {
      if (!src && !runId) return
      setLoading(true)
      setError(null)
      try {
        const data = src
          ? await api.fetchJson(src)
          : await api.getRun(runId)
        if (!cancelled) setRun(data)
      } catch (e) {
        if (!cancelled) setError(e.message)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [src, runId])

  // Drag-and-drop handler for arbitrary run JSON files
  function onDrop(e) {
    e.preventDefault()
    const file = e.dataTransfer.files[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = () => {
      try { setRun(JSON.parse(reader.result)) }
      catch (err) { setError(`Failed to parse JSON: ${err.message}`) }
    }
    reader.readAsText(file)
  }

  function reload() {
    if (runId) api.getRun(runId).then(setRun).catch(e => setError(e.message))
    else if (src) api.fetchJson(src).then(setRun).catch(e => setError(e.message))
  }

  return (
    <div
      style={styles.root}
      onDragOver={e => e.preventDefault()}
      onDrop={onDrop}
    >
      {loading && <div style={styles.empty}>Loading run…</div>}
      {error && <div style={styles.errBox}>{error}</div>}
      {!loading && !run && !error && (
        <div style={styles.empty}>
          <div style={styles.emptyTitle}>Loom Replay</div>
          <div style={styles.emptyHint}>
            Load a run by:
            <ul style={styles.emptyList}>
              <li><code>?src=&lt;url-to-run.json&gt;</code> in the URL</li>
              <li><code>?run=&lt;run_id&gt;</code> (requires serve.py running)</li>
              <li>drag-and-drop a run JSON file onto this page</li>
            </ul>
          </div>
        </div>
      )}
      {run && <LoomPlayer run={run} onReload={runId ? reload : undefined} />}
    </div>
  )
}

const styles = {
  root: { display: 'flex', flexDirection: 'column', height: '100vh', background: '#0e0e18', color: '#e8e8f0', fontFamily: 'monospace' },
  empty: { color: '#888', padding: 40, fontSize: 13, textAlign: 'center', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', flex: 1 },
  emptyTitle: { fontSize: 20, color: '#c084fc', marginBottom: 16, fontWeight: 600 },
  emptyHint: { maxWidth: 480, lineHeight: 1.6 },
  emptyList: { marginTop: 12, marginLeft: 24, textAlign: 'left' },
  errBox: { color: '#f87171', padding: 16, fontSize: 12, borderTop: '1px solid #1e1e2e' },
}
