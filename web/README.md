# loom-web

React components and standalone admin UI for [loom_agentic](../).
Two consumption modes:

1. **Standalone admin app** — Vite SPA, served by `loom_agentic.serve`
2. **Component library** — `import { LoomPlayer, AdminNav } from 'loom-web'`

## Standalone admin app

The default `npm run dev` / `npm run build` produces a self-contained
React app in `dist/`. `loom_agentic.serve` mounts that dist and exposes
`/api/runs`, `/api/runs/{id}`, etc. for the app to consume.

```bash
# Dev (hot reload):
cd web/
npm install
npm run dev          # http://localhost:5173

# Production build for serve.py:
npm run build        # produces dist/
LOOM_EVENTLOG_PATH=/path/to/events.jsonl python -m loom_agentic.serve
# http://localhost:5174
```

## Component library

Other React projects can consume loom-web's components without forking
or copying source files. Run `npm run build:lib` to produce `dist-lib/`,
then install from a file path or (eventually) npm.

### In the consumer's `package.json`:

```json
{
  "dependencies": {
    "loom-web": "file:../path/to/loom_agentic/web"
  }
}
```

### In consumer code:

```jsx
import { LoomPlayer, AdminNav } from 'loom-web'
import 'loom-web/styles.css'      // optional global resets

function MyAdmin() {
  return (
    <>
      <AdminNav
        wordmark="MY APP"
        routes={[
          { path: '/replay',     label: 'Replay' },
          { path: '/my-thing',   label: 'My Thing' },
        ]}
      />
      <LoomPlayer run={runJson} />
    </>
  )
}
```

### Peer dependencies

The library externalises React, react-dom, react-router-dom, and mermaid
so consumers control the versions and avoid duplicate React instances
(which break hooks). Install in the consumer:

```bash
npm install react react-dom react-router-dom mermaid
```

`react-router-dom` is marked optional — only required if you use
`AdminNav` (which uses `Link` and `useLocation`). `LoomPlayer` works
without it.

## Exported components

| Component   | Purpose                                                 |
|-------------|---------------------------------------------------------|
| `LoomPlayer`| Render a single agent run with frame-stepping playback. Consumes the JSON shape from `loom_agentic.replay.serialize_run()`. |
| `AdminNav`  | Top bar with route links + active-link highlighting.     |

Page-level views (`Replay`, `Sessions`, `Scorecards`) are NOT exported.
Pages are app-specific composition — consumers build their own from the
components above.

## Build outputs

```
web/
  dist/         ← SPA build (npm run build) — what serve.py mounts
  dist-lib/     ← Library build (npm run build:lib) — what consumers import
    loom-web.js     — ESM entry, sourcemapped, unminified
```

Both targets coexist; running one doesn't disturb the other.
