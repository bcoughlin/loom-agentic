# 2026-04-30 — policy + eventlog + stepper extension (plan 0)

## Scope

Built loom's `policy` and `eventlog` packages plus extended `replay/stepper.py`
to consume `on_position_report` events. README/DOCS described all of this but
none of it was implemented. Vibeplan at
`vibeplan/20260430_plan_0_policy_primitives.md`.

## What was built

### `loom_agentic/policy/`
- `model.py` — `Policy` and `EdgePrompt` frozen dataclasses
- `loader.py` — `load_policy(name, search_dirs)` reads `<name>.policy.mmd`
  + `<name>.policy.yaml` from disk, validates yaml refs against mermaid
  nodes, computes sha256[:8] over .mmd bytes. YAML edits don't change sha
  (deliberate — barrier fires only on structural change)
- `render.py` — `render_prompt_section(policy)` produces the 4-section
  block: header + invariants + flowchart + per-node/edge guidance + position
  contract listing all node ids
- `tool.py` — `report_position_tool(policy)` returns provider-agnostic JSON
  Schema with `node_id` enum bound to `policy.node_ids`. `extra_properties`
  hook for plan 1 (`working_memory_patch`) — single-line addition later
- `barrier.py` — `policy_update_barrier_message(...)` string template
- 26 tests across loader/render/tool/barrier with fixtures

### `loom_agentic/eventlog/`
- `writer.py` — `EventWriter` with typed helpers per event type
  (`emit_graph_structure`, `emit_position_report`, `emit_chat_model_end`,
  `emit_tool_start`/`end`, etc.). Auto-creates parent dir, thread-locked
  appends, auto-stamps `policy_version` + `policy_sha` on every record.
  Defaults `thread_id == run_id` when not supplied
- 10 tests including round-trip through `replay.loader` and `frames_for_run`

### `replay/stepper.py` extension
- `STORY_EVENTS` now includes `on_position_report`
- New Frame branch for position reports — `active_node = node_id`,
  📍 prefix in summary, sets `reported_node_id` + `reported_rationale`
- Tool frames inherit the most-recent `last_reported_node` so the chart
  highlight ties back to the authored policy node, not just the tool name
- Falls back to the existing ReAct topology (`agent` node) when no position
  report precedes a tool call — existing LangGraph runs render unchanged
- `Frame` dataclass gains `reported_node_id` + `reported_rationale`
- `serialize_run` exposes both fields to player.html

### `orchestrate/__init__.py`
- Lazy-loaded langgraph-dependent symbols via PEP 562 `__getattr__`
- `policy` + `eventlog` can now be used without langgraph installed
- Public API unchanged (`from loom_agentic.orchestrate import build_from_mermaid`
  still works, just defers the heavy import)

### Top-level
- Bumped to v0.0.2
- Added `pyyaml>=6.0` as base dependency
- Updated `__init__.py` docstring to describe four modes (was three)

## Test results

38/38 pass. Critical assertions:
- `node_id` enum on `report_position` matches policy's declared node ids
  exactly (closes layer-4 enforcement gap — Anthropic API rejects
  out-of-vocabulary calls before reaching handlers)
- Position report drives `active_node` in stepper
- Tool frame after a position report inherits both `reported_node_id`
  and `active_edge[0]` (anchor at reported node, not "agent")
- Tool frame WITHOUT a preceding position report still anchors at
  "agent" (LangGraph backward-compat preserved)
- YAML referencing a node not in `.mmd` raises `PolicyLoadError`
  (catches typos at load time)
- Render section ordering is mermaid declaration order, not yaml order

## Findings worth recording

1. **README was aspirational.** Multiple primitives described (load_policy,
   render_prompt_section, report_position) had zero code behind them.
   The replay-side infrastructure WAS more loom-aware than I assumed —
   `on_graph_structure`, `on_context_carry`, `on_policy_update` events
   already supported by loader/serializer/stepper synthetic markers.
2. **Terminology collision flagged.** Loom already uses "context carry"
   (`on_context_carry`) for "the verbatim system prompt the agent READ."
   Plan 1's "reasoning carry" was a different concept (agent-emitted
   structured working state). Plan 1 doc updated to flag the rename
   need (`working_memory` or `reasoning_state`) before implementation.
3. **Stepper hardcoded ReAct vocabulary** — fixed via additive
   `on_position_report` branch. Did NOT replace the existing
   `on_chat_model_end` / `on_tool_start` / `on_tool_end` handling — both
   coexist so LangGraph and loom-policy runtimes can share replay UI.
4. **PEP 562 lazy module-level `__getattr__`** is the clean fix for the
   "submodule needs sibling-submodule's parser without triggering the
   parent package's heavy imports" pattern. Worth remembering.

## Open / next

- **Plan 0b (kepler integration)** — wire `EventWriter` into kepler's
  director loop, author `kepler_director.policy.mmd` + `.yaml`, append
  `policy.render_prompt_section()` to `_system_prompt_for_session()`,
  add `report_position_tool(policy)` to `DIRECTOR_TOOLS`. New endpoint
  `/director/session/{sid}/replay` serves `player.html` with the run JSON.
- **Plan 1 (working memory observability + thinking capture)** — needs
  the rename from "reasoning carry" first. Build on top of 0b once
  there's a real session producing replay artifacts.
- **DOCS.md / README updates** — deferred. Code shipped; docs sync next
  session before plan 0b lands.

## Commit

`ef29cd6` — Add policy, eventlog, and on_position_report stepper support
