# 2026-05-02 batch 1 — scorecard module + web module plans + library mode

Long session (work spanned 2026-05-01 → 2026-05-02). Loom gained
three architectural plans, a working web admin scaffold, a published
component library, and a vibespark connecting the scorecard concept
to fine-tuning data generation.

## What landed

### Plan 2 — scorecard module

`vibeplan/20260501_plan_2_scorecard_module.md` — full design for a
new `loom_agentic/scorecard/` sibling module:

- **Per-agent YAML charters** with anchored-level rubrics (5 = X,
  3 = Y, 1 = Z), evidence requirements, and edge cases. Worked
  example for `claims_match_reality` written directly from a real
  shale failure mode (the Katrina-loop session). Anti-patterns
  section explicitly says what NOT to write in a rubric.
- **Three score sources**: self (agent in-loop), judge LLM (Haiku,
  post-hoc), human (UI). Disagreements are themselves signal.
- **Toggle config** per agent. Modes: `post_hoc`, `self_score`, both.
- **Five reinforcement levers** in increasing automation: pure
  transparency (recommended start), in-context score reminder,
  constraint promotion (wires to shale's existing constraints
  system), capability gating, charter revision via failure examples.
- Honest framing: "reinforcement without weights is iterative prompt
  design with a feedback loop." Scorecards don't train the agent;
  they train the human (or a prompt-tuning agent) to make better
  prompts.

### Plan 3 — web module + library mode (substantially built)

`vibeplan/20260501_plan_3_web_module.md` — design + implementation
for `loom_agentic/web/` and `loom_agentic.serve`. Sequence:

- ✅ Bootstrap `web/` (vite, react 18, react-router-dom, mermaid)
- ✅ Upstream `LoomPlayer.jsx` from powra-mobile-app verbatim.
  Audit confirmed only `react`+`mermaid` imports, zero powra
  coupling. Plan_3's premise validated.
- ✅ Generalize `AdminNav.jsx` with `routes`/`wordmark`/`right`
  props, longest-prefix active match
- ✅ `serve.py` — FastAPI at `loom_agentic/serve.py`. Endpoints:
  `/api/health`, `/api/runs?hours=N&agent=X&limit=N`,
  `/api/runs/{id}`, `/api/agents`. SPA mount with client-side
  routing fallback. Lazy fastapi import. `web` extra added to
  `pyproject.toml`.
- ✅ **Library mode** — `vite.config.lib.js` produces a consumable
  ESM bundle (~43KB, peer deps externalized). `web/src/index.js`
  re-exports `LoomPlayer` + `AdminNav`. `package.json` has
  `main`/`module`/`exports`/`peerDependencies`. `web/README.md`
  documents both consumption modes.
- ⏭ Step 5 (SessionList + SessionDetail), 6 (EventLogPanel), 8
  (end-to-end verify with real eventlog) — next session
- ⏸ Step 9 (powra migration), 10 (scorecard pages) — later

### Vibespark — scorecards as training data

`vibespark/20260501_spark_1_scorecards_as_training_data.md` —
realization captured: the scorecard infrastructure also serves as
preference-pair training data for DPO. Same architectural decisions
in plan_2 enable both use cases at no extra cost. Adds **lever #6**
(preference-tune the agent itself) to plan_2's reinforcement
options. Honest hedge that this matters only at scoring volume
(~1000+ pairs per criterion); below that the scorecard's value is
purely measurement.

### Doc updates

- `README.md` — added "Web UI — two consumption modes" section,
  expanded repo layout tree to show `web/` structure, added `web`
  optional dep
- `DOCS.md` — comprehensive "Web UI module" section covering env
  vars, API endpoints, both consumption modes, what's not built yet
- `replay/static/player.html` — header note pointing at the React
  version, framing static player as the zero-dep choice (not the
  prototype)

### Decision flips captured

Two deferred decisions from plans got revisited and flipped during
the session, with the trigger named:

- **Plan_3 npm-package vs symlink:** original recommendation was
  symlink (less ceremony). User asked "so viz UI can't be pulled
  into another project as a module?" — answering "no, only via
  symlink today" felt wrong given the cost. Library mode shipped;
  plan_3 updated to flip the recommendation and document the trigger.
- **Plan_3 sequence step ordering:** built step 7 (serve.py) before
  step 5 (SessionList) because real `/api/runs` data made step 5
  cleaner. Plan updated with status legend documenting actual
  landed order vs originally-planned order.

## Cross-repo connections

This session's work in loom connects to:

- **proving-shale** — the Katrina-loop session became the worked
  example for plan_2's `claims_match_reality` rubric. The
  scorecard's first real test (when built) will be retroactively
  scoring that session against the rubric. Shale will eventually
  consume loom's policy + scorecard machinery (loom plan 4 — long-
  deferred shale-on-loom conversion, now has a forcing function).
- **proving-author-vellum** — vellum will eventually adopt loom's
  policy primitives + use loom-web's components (especially
  `EventLogPanel` for displaying authoring events, `LoomPlayer` for
  inline transcript review in scorecard session detail).
- **powra-mobile-app** — the de-facto upstream for the React UI.
  Plan_3 step 9 (when scheduled) migrates powra to consume `loom-web`
  as a real npm-style dep instead of forking the source.

See shale's `vibelog/20260502_batch_1_data_integrity_cost_constraints.md`
and vellum's `vibelog/20260502_batch_1_scaffold_and_shale_read.md`
for matching session records.

## What's still open

Ranked:

1. **Continue plan_3 web work** — steps 5, 6, 8 (~30-60 min total).
   SessionList + SessionDetail + EventLogPanel make the admin surface
   actually useful for browsing runs.
2. **Plan_2 first slice** — charter loader + score store + post-hoc
   judge runner + manually score the Katrina session. ~2 hours.
   Validates the entire scorecard concept against a known failure case.
3. **Powra migration** — convert powra-mobile-app to consume `loom-web`
   via file-path install. Sets the consumption pattern correctly before
   any third consumer (vellum, kepler) appears.
4. **Plan_2 in-context reminder + constraint promotion** — once
   plan_2 has produced real failure patterns, levers #2 and #3 wire
   the feedback loop back into the agent.

## Honest hedges

- **`serve.py` verified with empty eventlog only.** Endpoints return
  shape correctly, SPA routes resolve, but full path through real
  loom-format JSONL → grouped runs → frames in the player needs a
  real eventlog to validate. Not blocking; just untested at this
  layer.
- **No TypeScript types in the library.** `package.json` declares
  `"types": "./dist-lib/loom-web.d.ts"` but the file doesn't exist.
  Consumers using TypeScript will get `any`. Fix: hand-write `.d.ts`
  files, OR migrate components to TypeScript later. Not blocking
  for current consumers (powra is plain JSX).
- **CSS is minimal.** Components use inline styles (powra
  convention). `loom-web/styles.css` exports just global resets. If
  third consumer with different visual identity appears, this needs
  to evolve toward CSS variables on `:root`.
- **Library not published to npm.** File-path install works for local
  dev. Going to npm needs publishable name + scope decision +
  release process. Defer until you actually want public consumption.
