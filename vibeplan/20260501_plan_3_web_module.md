# Plan 3 — Web module for loom_agentic

## Problem statement

Loom today has one UI artifact: `loom_agentic/replay/static/player.html`
(~260 lines, self-contained, drag-and-drop). It works for replaying
one run with no build step.

Meanwhile, **powra-mobile-app/web has been quietly building the
production version of loom's UI**:

- `LoomPlayer.jsx` (1016 lines) is a substantially improved replay
  player — frame stepping with reported/inferred position tracking,
  smooth playback, tool-call snippets with copy buttons, total
  elapsed indicators
- `AdminAgentRuns.jsx` (282 lines) is a two-column list+detail page
  for browsing runs by time-window and agent filter
- `AdminNav.jsx` (100 lines) — extensible nav across admin pages
- `LogViewerPanel.jsx` (172 lines) — scrollable event log viewer
- Visual conventions, dark theme, monospace tone all dialed in

The author of `LoomPlayer.jsx` even left a comment: *"When loom_agentic
eventually ships its own JS package, this component becomes a thin
wrapper over it."* The expectation was always that this work would
flow back. It hasn't, and the static player.html in loom is now a
prototype that drifts further from the production form every session.

This plan defines **how the powra-side work upstreams into loom**,
what loom's web module looks like, how powra-mobile-app converts to
consume loom (instead of forking it), and how the scorecard UI from
plan_2 plugs in.

## What this plan does NOT do

- Implement scorecard views (those are plan_2's `ui.py` deliverables;
  this plan provides the surface they land on)
- Convert powra-mobile-app's web/ — that's its own follow-up; this
  plan defines the migration path
- Replace `replay/static/player.html` — that stays for the no-build
  use case (drop-in replay of a single run JSON file)
- Build the scorecard pages themselves
- Decide hosting (local dev only for v1; deployment is consumer concern)

## Architecture — new sibling module

```
loom_agentic/
  web/                          ← new directory, vite/react app
    package.json
    vite.config.js
    index.html
    .gitignore                  — node_modules, dist
    src/
      App.jsx                   — routes
      main.jsx
      lib/
        api.js                  — generic REST client (no auth assumptions)
      components/
        LoomPlayer.jsx          — UPSTREAMED from powra-mobile-app
        AdminNav.jsx            — UPSTREAMED, stripped of powra deps
        SessionList.jsx         — extracted from AdminAgentRuns left col
        SessionDetail.jsx       — extracted from AdminAgentRuns right col
        EventLogPanel.jsx       — UPSTREAMED from LogViewerPanel, generalized
      pages/
        Replay.jsx              — single-run replay (wraps LoomPlayer)
        Sessions.jsx            — list of agent runs (sessions)
        Scorecards.jsx          — list of charters with rolling averages [plan_2]
        ScorecardDetail.jsx     — single charter view [plan_2]
        SessionScoring.jsx      — self/judge/human side-by-side [plan_2]
  serve.py                      — FastAPI: mounts built dist/, serves
                                  /api/runs, /api/sessions,
                                  /api/scorecards, /api/charters
                                  reading from eventlog + scorecard store
  replay/static/player.html     — UNCHANGED, stays for no-build use case
```

**Two surfaces, one source of truth on the React side:**

- The Vite build produces `loom_agentic/web/dist/` — served by
  `serve.py` for the rich admin experience
- `replay/static/player.html` stays as the zero-dependency drop-in
  for "I have one JSON, give me a renderer" use cases (consumer
  embeds it as an iframe, opens it as a file, etc.)

These never need to be kept in sync feature-by-feature. The static
player is intentionally minimal; the React app is where active
development happens.

## Stack decision

Match what powra-mobile-app already uses — no reason to diverge:

- **Vite** for build (fast, no config bloat)
- **React 18**
- **react-router-dom** for multi-page nav (Replay, Sessions, Scorecards)
- **mermaid** loaded as a npm dep (not CDN — the static player keeps
  CDN load for zero-dep)
- **No Tailwind, no styled-components.** Inline `styles` object at
  the bottom of each file. Powra's convention; works well for an
  admin surface; keeps each file readable in isolation.
- **No state management library.** Component state + prop drilling
  for now. URL state via react-router for shareable views.
- **No TypeScript.** Plain JSX, JSDoc when types matter. Match
  powra's tone; lower friction for upstreaming.

## What gets upstreamed (file by file)

### 1. `LoomPlayer.jsx` (powra-mobile-app/web/src/components/) → `loom_agentic/web/src/components/LoomPlayer.jsx`

- Move verbatim. The component is already framework-light.
- Strip nothing — it doesn't have powra-specific deps.
- Becomes the canonical replay component. Powra-mobile-app will
  re-import it from `loom_agentic/web` as a dep (see Migration below).

### 2. `AdminNav.jsx` → `loom_agentic/web/src/components/AdminNav.jsx`

- Keep the visual structure.
- Replace hardcoded powra route names with a `routes={[...]}` prop:
  ```jsx
  <AdminNav routes={[
    {path: '/replay', label: 'Replay'},
    {path: '/sessions', label: 'Sessions'},
    {path: '/scorecards', label: 'Scorecards'},
  ]} />
  ```
- Powra wraps it with its own routes added on top.

### 3. `AdminAgentRuns.jsx` two-column pattern → `SessionList.jsx` + `SessionDetail.jsx`

- Don't move whole-file. Extract the list+detail pattern.
- `SessionList`: takes `items, selectedId, onSelect, filters, onRefresh`,
  renders the filtered list with refresh button.
- `SessionDetail`: takes `item, loading`, renders the right pane.
- The `runLabel()` powra thread-parsing logic stays powra-side. Loom's
  generic version uses `item.label || item.id`.

### 4. `LogViewerPanel.jsx` → `EventLogPanel.jsx`

- Generalize. Today it has a `summaryLine(ev)` switch on
  powra-specific event types (`classify_screen`, `identify_entity`,
  etc.). Replace with a `summarizer={ev => string}` prop so each
  consumer plugs in its own.
- Keep the polling + auto-scroll + status badge UI.

### 5. `api.js` → `loom_agentic/web/src/lib/api.js`

- Strip cookie-auth. Generic `fetch` wrapper with error handling.
- Configurable base URL via `import.meta.env.VITE_LOOM_API_BASE`.

## `serve.py` shape

A single FastAPI app that:

- Serves `loom_agentic/web/dist/` as static files at `/`
- Exposes JSON endpoints for the React app:
  - `GET /api/runs?hours=N&agent=X` — list of runs from eventlog
  - `GET /api/runs/{run_id}` — single run with frames (matches
    `loom_agentic.replay.serialize_run()` shape)
  - `GET /api/charters` — list of available charters [plan_2]
  - `GET /api/charters/{agent}` — single charter [plan_2]
  - `GET /api/scores?agent=X&since=...` — score events [plan_2]
- Has a flag for dev mode (proxies to vite dev server on :5173 for
  hot reload) vs prod mode (serves the built dist/)
- Defaults to localhost-only binding; consumers can rebind for
  network access

Not implementing auth in v1. Loom's web module is a developer/admin
tool; if exposed to a network, the consumer is responsible for
fronting it with auth.

## Migration path for powra-mobile-app

The goal: powra-mobile-app stops forking and starts consuming. Two
realistic shapes for "consuming loom's web":

**Option X — npm-package style.** Loom publishes `@loom/web` to npm
(or a local file path during dev). Powra adds it as a dep and imports
components directly. Cleanest separation; needs npm publishing
discipline.

**Option Y — git-submodule / file-symlink.** Loom's `web/src/` is
referenced from powra via symlink or submodule. No publishing
overhead; tighter coupling.

**Original recommendation: Y.** Less ceremony. Loom isn't ready for npm
publishing discipline yet. When loom matures or a third consumer
appears (vellum could be one), revisit X.

> **DECISION REVISITED AND FLIPPED (same session, prior to powra
> migration starting).** The trigger was the user asking *"so viz UI
> can't be pulled into another project as a module?"* — answering
> "no, only via symlink today" felt wrong given how small the cost was
> to make it real. Library mode shipped: `web/vite.config.lib.js`,
> `web/src/index.js` re-export entry, `package.json` updated with
> `main`/`module`/`exports`/`peerDependencies`. See `web/README.md`.
>
> **Today's recommendation: X (npm-package style), via file-path
> install.** Consumer adds `"loom-web": "file:../loom_agentic/web"`
> and imports normally. No npm-publish discipline required yet (defer
> until you actually want public publishing). Library bundle is
> ~43KB ESM with React/mermaid externalized as peers — clean
> separation, no source-file forking, single React instance in
> consumer.

Powra-mobile-app's conversion flow (updated to use library mode):
1. ✅ Loom's web module ships (this plan delivers the scaffolding)
2. Powra `web/src/components/LoomPlayer.jsx` becomes a one-line re-export:
   ```jsx
   export { LoomPlayer as default } from 'loom-web'
   ```
3. Powra `web/src/pages/AdminAgentRuns.jsx` keeps its powra-specific
   logic (run-label parsing, agent filter); imports `LoomPlayer` from
   `loom-web` instead of local file
4. Powra `web/src/components/LogViewerPanel.jsx` becomes a thin
   wrapper that imports loom's `EventLogPanel` and passes
   `summarizer={powraSummarizer}` (once `EventLogPanel` lands —
   plan_3 step 6)
5. Powra-specific pages (`AdminGameState`, `AdminHippocampus`,
   `AdminSubstrate`, etc.) stay powra-side as before
6. Powra adds `loom-web` as a `file:` dep, declares peer deps
   (already has react, react-dom, react-router-dom, mermaid)

Powra keeps its auth, its domain pages, its routing on top. Loom owns
the generic admin surface and the replay player. Updates to loom's
components require a `npm run build:lib` in loom's repo + a
`npm install` in powra's repo to pick up the new dist-lib bundle.

## How plan_2 (scorecards) plugs in

Plan_2 deferred its UI to "when loom grows a UI surface." This plan
provides that surface. Sequencing:

- This plan lands first → loom has `web/`, has `serve.py`, has the
  list+detail pattern in components
- Plan_2's deferred UI work becomes: add `Scorecards.jsx`,
  `ScorecardDetail.jsx`, `SessionScoring.jsx` pages that consume
  loom's existing components (`SessionList` for the list,
  `SessionDetail` shape for the per-session score breakdown)
- Score events come from the eventlog via `serve.py`'s
  `/api/scores` endpoint
- The "side-by-side self/judge/human" view is just three columns of
  scores — straightforward render against the score event shape

The dependency arrow runs plan_3 → plan_2's UI deliverables. Plan_2's
non-UI parts (charter loader, runner, store, in-context reminder)
don't depend on this plan and can ship in parallel.

## Implementation sequence

> Status legend: ✅ done · ⏭ next · ⏸ deferred (waits on something)
>
> **Order note:** the plan listed step 5 (SessionList/SessionDetail)
> before step 7 (serve.py). In practice 7 was done first because real
> `/api/runs` data made step 5 cleaner (no mock-data shape drift). The
> reordering wasn't a problem; documenting it so the next reader sees
> the actual landed order.

1. ✅ **Doc this plan** — captured here.
2. ✅ **Bootstrap `loom_agentic/web/`** — package.json, vite.config.js,
   src skeleton, App.jsx, both `npm run build` and `npm run dev` clean.
3. ✅ **Move `LoomPlayer.jsx` from powra** — verbatim copy. Audit
   confirmed only `react` + `mermaid` imports — zero powra coupling.
4. ✅ **Generalize `AdminNav.jsx`** — `routes` + `wordmark` + `right`
   props. Longest-prefix active match. Wired into App.jsx.
5. ⏭ **Extract `SessionList.jsx` + `SessionDetail.jsx`** from
   AdminAgentRuns pattern, plug into `Sessions.jsx` page.
6. ⏭ **Generalize `LogViewerPanel.jsx` → `EventLogPanel.jsx`** with
   summarizer prop.
7. ✅ **Build `serve.py`** — FastAPI at `loom_agentic/loom_agentic/serve.py`,
   `/api/health`, `/api/runs`, `/api/runs/{id}`, `/api/agents`. SPA mount
   with client-side routing fallback. Lazy fastapi import. `web` extra
   added to `pyproject.toml`.
8. ⏭ **Verify end-to-end with real eventlog** — point
   `LOOM_EVENTLOG_PATH` at a real loom-format JSONL, browse runs in the
   UI, click through to LoomPlayer rendering. (Endpoints verified with
   empty eventlog; full path needs real data.)
9. ⏸ **Migrate powra-mobile-app** — install `loom-web` via file-path
   dep (library mode shipped — see decision flip above), one-line
   re-export shim for powra's existing LoomPlayer.jsx, then progressively
   replace AdminNav and LogViewerPanel.
10. ⏸ **Plan_2 UI deliverables** — Scorecards, ScorecardDetail,
    SessionScoring pages

Steps 1-8 are this plan. Steps 9-10 are follow-ons.

## Files this plan creates

- `loom_agentic/web/package.json`
- `loom_agentic/web/vite.config.js`
- `loom_agentic/web/index.html`
- `loom_agentic/web/.gitignore`
- `loom_agentic/web/src/main.jsx`
- `loom_agentic/web/src/App.jsx`
- `loom_agentic/web/src/lib/api.js`
- `loom_agentic/web/src/components/LoomPlayer.jsx` (upstreamed)
- `loom_agentic/web/src/components/AdminNav.jsx` (upstreamed, generalized)
- `loom_agentic/web/src/components/SessionList.jsx` (extracted)
- `loom_agentic/web/src/components/SessionDetail.jsx` (extracted)
- `loom_agentic/web/src/components/EventLogPanel.jsx` (upstreamed,
  generalized)
- `loom_agentic/web/src/pages/Replay.jsx`
- `loom_agentic/web/src/pages/Sessions.jsx`
- `loom_agentic/serve.py`
- Updates to `loom_agentic/__init__.py` to expose `serve` if helpful

## Open questions

- **Where does the eventlog live for the API to read?** Today
  loom_agentic's eventlog writes to wherever the consumer configures
  it. For `serve.py` to read it, it needs a known path. Options: env
  var `LOOM_EVENTLOG_PATH`, CLI flag to `serve.py`, or config file.
  Defer to implementation; env var is cheapest.
- **Multiple agents writing to one eventlog vs per-agent eventlogs.**
  Today's pattern in powra is per-agent. The list-of-runs view
  assumes one log per agent OR one mixed log with `agent` field.
  Both work; need to confirm the powra shape and match.
- **Live tail vs polled refresh.** Powra's UI polls every 5s
  (`POLL_MS = 5000` in LogViewerPanel). Live SSE would be nicer; not
  worth building until polling becomes felt.
- **What about styling drift?** Today powra hardcodes the dark theme
  in inline styles. If loom gets a third consumer with different
  brand, the inline styles approach won't scale. Cross that bridge
  then; CSS variables on `:root` is the cheapest abstraction.
- **Build artifact in git?** `dist/` should be gitignored; consumers
  build locally. But for `serve.py` to work without `npm run build`
  every time, may need a "fallback to CDN-loaded version" path.
  Defer; gitignore by default.

## Out of scope

- Auth (consumer concern)
- Deployment / hosting
- npm package publishing (deferred until a third consumer exists)
- Migrating powra-mobile-app's web/ — separate follow-on
- Replacing `replay/static/player.html` — stays for the no-build use case
- Vellum's adoption of loom's web (separate plan when vellum needs UI
  beyond its current diff viewer)
- Scorecard pages themselves (plan_2's UI deliverables, post this plan)

## What this plan DOES NOT lock in

- The npm-package vs symlink consumer model (recommends symlink for v1,
  X is open)
- The exact /api/* shapes (sketched, not specified — implementation
  refines them)
- TypeScript adoption (currently no; reconsider if components grow
  past ~500 LOC each)
- A state management library (currently no; reconsider if multiple
  pages need shared state)
- The eventlog path discovery mechanism

## Honest hedge

The biggest unknown is the **upstreaming friction**. powra-mobile-app
has been the canonical UI host for months; pulling components out
might surface implicit dependencies on powra's API shape, environment
variables, or routing assumptions that aren't visible from a static
read. Step 9 (migrate powra to consume loom) is the moment those
emerge. Plan accordingly: budget extra time for that step or accept
that powra and loom may need a brief period of dual-maintenance while
the seams are worked out.

The smaller hedge: **inline styles don't scale across consumers with
different visual identities**. For loom + powra (one consumer today),
they're fine. If vellum or kepler gets a UI built against loom's
components, the styling story needs to evolve toward CSS variables
or at minimum a theme prop. Not a v1 problem; flagged so future-us
doesn't get surprised.
