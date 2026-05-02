/**
 * Generic REST client for loom_agentic's web UI.
 *
 * No auth assumptions — auth is the consumer's responsibility. If
 * loom's serve.py is exposed beyond localhost, the consumer fronts
 * it with their own auth layer (reverse proxy, cookie middleware,
 * etc.).
 *
 * Base URL via VITE_LOOM_API_BASE (defaults to "" so same-origin
 * works when serve.py mounts the dist at /).
 */

const BASE = import.meta.env.VITE_LOOM_API_BASE || ''

async function request(method, path, body) {
  const opts = {
    method,
    headers: { 'Content-Type': 'application/json' },
  }
  if (body !== undefined) {
    opts.body = JSON.stringify(body)
  }
  const res = await fetch(`${BASE}${path}`, opts)
  const json = await res.json().catch(() => ({}))
  if (!res.ok) {
    const err = new Error(json.error || `HTTP ${res.status}`)
    err.status = res.status
    throw err
  }
  return json
}

export const api = {
  // Runs (replays)
  listRuns: (hours = 24, agent) =>
    request('GET', `/api/runs?hours=${hours}` + (agent ? `&agent=${encodeURIComponent(agent)}` : '')),
  getRun: (runId) => request('GET', `/api/runs/${encodeURIComponent(runId)}`),

  // Generic raw fetch — useful when loading run JSON from any URL,
  // including local files served via ?src= query param in the player.
  fetchJson: async (url) => {
    const res = await fetch(url)
    if (!res.ok) throw new Error(`HTTP ${res.status} fetching ${url}`)
    return res.json()
  },
}
