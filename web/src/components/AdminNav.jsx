import { Link, useLocation } from 'react-router-dom'

/**
 * Shared top bar for loom_agentic's web admin surface.
 *
 * Generic version — accepts routes via prop instead of hardcoding,
 * so consumers (powra, vellum, future repos) can compose loom's nav
 * with their own routes layered on top, or replace the wordmark/right
 * slot entirely.
 *
 * Props:
 *   routes      — [{ path, label }, ...] — links rendered in order
 *   wordmark    — string for the left-side title; defaults to "LOOM"
 *   right       — optional ReactNode rendered in the right-aligned slot
 *                 (e.g. profile name, env badge, refresh control)
 *
 * Active-link detection is path-prefix based — a route at `/scorecards`
 * matches `/scorecards`, `/scorecards/`, and `/scorecards/anything`. This
 * matches how nested routes feel in practice; the deepest-prefix wins
 * when multiple routes match.
 */
export default function AdminNav({ routes = [], wordmark = 'LOOM', right }) {
  const { pathname } = useLocation()
  const normalized = pathname.replace(/\/$/, '') || '/'

  // Pick the longest-prefix match so `/scorecards/foo` activates the
  // `/scorecards` link, not `/`.
  let activePath = null
  let activeLen = -1
  for (const r of routes) {
    const rp = r.path.replace(/\/$/, '') || '/'
    if (normalized === rp || normalized.startsWith(rp === '/' ? '/' : rp + '/')) {
      if (rp.length > activeLen) {
        activePath = r.path
        activeLen = rp.length
      }
    }
  }

  return (
    <div style={styles.bar}>
      <div style={styles.wordmark}>{wordmark}</div>

      <nav style={styles.nav}>
        {routes.map(r => {
          const active = r.path === activePath
          return (
            <Link
              key={r.path}
              to={r.path}
              style={{ ...styles.link, ...(active ? styles.linkActive : {}) }}
            >
              {r.label}
            </Link>
          )
        })}
      </nav>

      <div style={styles.right}>{right}</div>
    </div>
  )
}

const styles = {
  bar: {
    display: 'flex',
    alignItems: 'center',
    gap: 4,
    padding: '0 16px',
    height: 44,
    borderBottom: '1px solid #1e1e2e',
    background: '#111118',
    flexShrink: 0,
  },
  wordmark: {
    fontWeight: 800,
    letterSpacing: 2,
    color: '#fff',
    fontSize: 13,
    marginRight: 12,
    whiteSpace: 'nowrap',
  },
  nav: {
    display: 'flex',
    alignItems: 'center',
    gap: 2,
  },
  link: {
    color: '#555',
    fontSize: 12,
    fontWeight: 600,
    textDecoration: 'none',
    padding: '5px 10px',
    borderRadius: 6,
    transition: 'color 0.12s, background 0.12s',
    whiteSpace: 'nowrap',
  },
  linkActive: {
    color: '#e8e8f0',
    background: '#1e1e2e',
  },
  right: {
    marginLeft: 'auto',
    fontSize: 12,
    color: '#555',
    whiteSpace: 'nowrap',
  },
}
