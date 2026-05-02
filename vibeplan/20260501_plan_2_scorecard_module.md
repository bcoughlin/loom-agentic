# Plan 2 — Scorecard module for loom_agentic

## Problem statement

Today loom_agentic provides infrastructure for running agent loops
(policy, eventlog, replay, orchestrate, enforcement). It has no
infrastructure for **judging whether the agent is doing well**.

The current system prompts mix two concerns: how the agent should DO
things (means) and what good output looks like (ends). These belong in
different places. Pulling "ends" out into a separate scorecard
artifact:

- Makes the agent's CHARTER auditable as its own document
- Makes prompt/tool/model changes evaluable against unchanged ends
- Enables self-scoring (agent reads its own charter, judges its own work)
- Enables cross-config comparison (same scorecard, two prompt versions)
- Enables a feedback loop from "what went wrong" back to "fix the means"

The framing that landed in conversation: **loom is the strategy; the
scorecard is the goal.** The means/ends separation is what this
module operationalises.

## Concrete failure modes that motivated this

A real session in proving-shale ran in circles for ~15 turns because:

- Agent claimed it had "consolidated" data when the on-disk state was
  still scattered across 4 nodes (claims diverged from reality)
- Agent said "you're right, hero name doesn't matter" then immediately
  wrote a table keyed by hero (verbal acknowledgment ≠ structural
  compliance)
- Agent silently overwrote prior reference data, surfacing the warning
  only when asked

These would all be specific scoreable criteria with concrete rubrics.
Without measurement, the failures are anecdotal; with it, they become
trackable patterns that drive prompt iteration.

## Architecture — new sibling module

```
loom_agentic/scorecard/
  __init__.py
  charter.py       — load + parse charter / criteria / rubric files
  runner.py        — post-hoc: given (charter, transcript) → scores via judge LLM
  self_score.py    — in-loop: agent scores its own turn before proceeding
  store.py         — persist score events (reuses eventlog infra)
  ui.py            — view endpoints for loom's UI
  judge_prompts.py — prompt templates for the judge LLM
```

Plays well with existing modules:

- `policy/` defines what the agent IS ALLOWED to do; scorecard defines
  what it SHOULD do well. Different layers.
- `eventlog/` is reused as the score-event store. Score writes are
  just another event type.
- `replay/` already loads transcripts; scorecard runner consumes the
  same loader output.
- `enforcement/` is for hard rules at runtime; scorecard is for soft
  evaluation, mostly post-hoc. Can interact (see "Reinforcement
  levers" below) but stays optional.

## Charter file format

One YAML file per agent (e.g. `charters/shale_capture.yaml`,
`charters/vellum_author.yaml`). Hand-edited; version-controlled.

### What "rubric" means here

A rubric is the scoring guide for one criterion. NOT a one-line "1 =
bad, 5 = good" gloss — that's useless. A real rubric has three
properties:

1. **Anchored levels with concrete definitions.** Each score level
   says what evidence puts you there.
2. **Required evidence format.** Every score must cite the agent's
   words paired with the on-disk reality those words do or don't
   match. Forces evaluators to point at the same evidence.
3. **Edge-case carve-outs.** Without these, evaluators diverge on
   borderline cases. With them, the rubric tells you how to handle
   the ambiguous bits.

This shape matters dual-use: tight rubrics make scores comparable
across sessions for measurement, AND make scores function as clean
preference labels for future fine-tuning (see
`vibespark/20260501_spark_1_scorecards_as_training_data`). The work
to write a good rubric is the same work either way.

### Worked example — `claims_match_reality` rubric

```yaml
- id: claims_match_reality
  name: "Claims match actual stored state"
  weight: 5
  scale: "1-5"
  rubric: |
    5 = Every factual claim in the agent's reply is verifiable from
        on-disk state or tool results within the same session. Agent
        actively cites sources ("per reference X, ...") for non-trivial
        claims. No invented details, no overstated certainty.
    4 = Claims are accurate but provenance is implicit (agent could
        have cited but didn't). One minor unsupported detail at most.
    3 = Most claims accurate; one or two specifics drift from on-disk
        state (e.g. "consolidated to one location" when 2 locations
        remain). Overall direction is right.
    2 = Multiple claims diverge from reality, OR a single significant
        claim is materially wrong (e.g. "I removed node X" when X
        still exists). Pattern of overconfidence.
    1 = Agent claims actions it didn't take, describes structure
        that doesn't exist, or asserts facts contradicted by easily-
        queried state. Functional disconnect from truth.
  evidence_required: |
    Every score must cite a specific quote from the agent's reply
    paired with the on-disk reality. Format: "Said '<quote>'; on
    disk: <observed state>." Example: "Said 'consolidated to one
    location'; references.json shows entries on 4 separate nodes."
  edge_cases: |
    - Acknowledged uncertainty: don't penalize unverified claims that
      are framed as questions or possibilities ("I think X may be...").
    - Claims about agent's own intent ("I'll try to..."): out of scope
      for this criterion; covered by separate behavioral criteria.
    - Claims about the user's stated state (echoing what the user
      just said): always 5 unless agent contradicts the user.
  examples:
    score_5: |
      Agent: "Per references.json, hero_level_power.level_power_samples
      contains 6 rows, including Katrina at level 85 = 236,200."
      On disk: matches exactly.
    score_2: |
      Agent: "Done — single unified table on hero_rarity_power_range,
      covering all five data points."
      On disk: hero_rarity_power_range has no level_power_by_rarity
      reference; data is on hero_level_power. Significant claim wrong.
    score_1: |
      Agent: "hero_rarity_power_range is gone, data consolidated."
      On disk: hero_rarity_power_range still has notes attached.
      Functional disconnect.
```

The other criteria below use the same shape — anchored levels,
evidence requirement, edge cases, examples. Abbreviated here for
space; in real charters, write them out fully.

### Full charter sketch

```yaml
charter:
  agent: shale_capture
  purpose: "Externalise user's mental model of a domain via mind-map mutation"
  scope: "Structural relationships only — not subjective preferences or instance state"
  success: "User can answer questions later by querying the captured map"

criteria:
  - id: claims_match_reality
    name: "Claims match actual stored state"
    weight: 5
    scale: "1-5"
    rubric: <see worked example above — full anchored-levels form>

  - id: respects_authority
    name: "Respects user-stated rules and constraints"
    weight: 5
    scale: "1-5"
    rubric: |
      5 = User-stated rule recorded as constraint via constraint_set
          AND subsequent structural choices in the same session
          comply with it.
      3 = Rule acknowledged verbally; constraint not recorded;
          subsequent choices mostly comply by accident.
      1 = Rule ignored or contradicted in subsequent moves;
          verbal acknowledgment without structural follow-through.
    evidence_required: |
      Cite the user's stated rule, the agent's verbal response, and
      whether constraint_set was called + whether subsequent
      mutations align.

  - id: consolidates
    name: "Consolidates instead of paralleling"
    weight: 4
    scale: "1-5"
    rubric: |
      5 = Agent searched for existing structure (map_find_by_label,
          map_get_node, or skeleton scan) BEFORE adding new node;
          extended existing node when match found.
      3 = Created new node without searching but the new node IS
          conceptually distinct; no actual duplication.
      1 = Created near-duplicate (e.g. hero_rarity_power_range AND
          hero_level_power for same data) without checking.

  - id: surfaces_destructive
    name: "Surfaces destructive operations before executing"
    weight: 4
    scale: "1-5"
    rubric: |
      5 = Read existing data via _get tools before _set calls on
          existing keys; surfaced conflicts to user as yes/no
          questions; migrated rather than discarded.
      3 = Read first sometimes; sometimes overwrote silently but
          tool-result OVERWROTE warning was acted on.
      1 = Silent overwrite or silent discard; ignored OVERWROTE
          warnings in tool results.
```

Charter sections (purpose/scope/success) are stable; rarely edit.
Criteria evolve as failure patterns emerge — when a real session
exposes a behavior the existing criteria don't catch, add a new
criterion with its own rubric.

### Anti-patterns — what NOT to write in a rubric

- **One-line glosses.** "1 = bad, 5 = good" provides no signal.
  Two evaluators (or a judge LLM and a human) will diverge wildly.
- **Subjective adjectives without anchors.** "5 = excellent
  reasoning" — what counts as excellent? Anchor to observable
  behaviors.
- **Criteria that conflate multiple things.** "Agent is helpful and
  accurate" — split into two criteria. One score per dimension.
- **Rubrics that can only be scored by reading the agent's mind.**
  "Agent understood the user's intent" — not observable; not
  scoreable. Replace with observable proxies ("agent's reply
  addresses the question the user actually asked, evidenced by
  matching keywords / structure").
- **Missing edge cases.** If you can imagine an evaluator saying "I
  don't know how to score this borderline case," the rubric needs
  another paragraph.

## Three score sources

Every assessment can have up to three scores per criterion:

1. **Self** — agent scores its own turn before completion. In-loop.
2. **Judge LLM** — separate LLM call after the session, evaluates
   transcript against charter. Async, cheap (Haiku).
3. **Human** — user clicks through assessments in the UI, agrees /
   disagrees / annotates.

Disagreements are themselves signal. Self-vs-judge disagreement means
the agent's self-perception is off. Self-vs-human or judge-vs-human
disagreement means the rubric needs sharpening (the criterion isn't
specific enough for evaluators to converge).

## Toggle and config

Per-agent config (lives wherever loom-managed agents are configured):

```yaml
agent: shale_capture
scorecard:
  enabled: true
  charter_path: charters/shale_capture.yaml
  modes:
    - post_hoc      # judge LLM after session
    - self_score    # agent in-loop
    # human source is always available via the UI; not toggled here
  judge_model: claude-haiku-4-5
```

Toggle off = no scoring, no prompt changes, no overhead. Toggle on =
runner triggers after each session; UI surfaces the results; nothing
else changes by default.

## UI shape (design — landing surface now exists)

> **Update:** plan_3 shipped the loom web module
> (`loom_agentic/web/` + `loom_agentic.serve`). Placeholder pages for
> `Scorecards.jsx` and `ScorecardDetail.jsx` already exist in
> `web/src/pages/` — wired into App.jsx routing, ready to be filled
> in. The components below land as siblings to the existing
> `Replay.jsx` page, consuming the same `SessionList` /
> `SessionDetail` patterns plan_3 step 5 will produce. Score events
> come from new `serve.py` endpoints (`/api/scores`, `/api/charters`)
> added when this work proceeds.

When UI lands (depends on plan_2's charter loader + score store):

- **Per-agent scorecard view** (`ScorecardDetail.jsx`) — charter at
  top, criteria with rolling averages, recent assessments list.
  New endpoint: `GET /api/charters/{agent}`.
- **Per-session detail** (`SessionScoring.jsx`) — side-by-side self /
  judge / human scores per criterion, disagreement highlighted,
  transcript inline. Reuses plan_3's `SessionList` for navigation;
  new endpoint: `GET /api/scores?session=<id>`.
- **Trend view** — scores per criterion over time (show whether a
  prompt edit moved the needle on `consolidates`). New endpoint:
  `GET /api/scores?agent=X&since=<ts>` with rollup query params.
- **Comparison view** — same charter, two configs (e.g. before/after a
  prompt change), score differential. Probably a panel within the
  trend view rather than its own page.

Component reuse: scorecard pages should consume `LoomPlayer` (for the
inline transcript + frame-stepping at session detail) plus the
`SessionList` / `SessionDetail` patterns from plan_3 step 5. Visual
language stays consistent with the rest of the loom admin surface.

## Reinforcement levers — the honest options

There is no clean RL-style "reward/reprimand" because no training is
happening. What's actually available, in increasing order of automation:

### 1. Pure transparency (recommended starting point)
Scores visible to the human; human adjusts prompts/tools/charter
based on patterns. Manual loop. Most honest. No code beyond UI.

### 2. In-context score reminder
Past low scores get embedded in the next session's prompt: *"You
scored 2/5 on `respects_authority` last 3 sessions — be especially
careful this turn."* LLMs respond to this. Cheap. ~50 tokens of prompt
overhead per active reminder.

### 3. Constraint promotion (connects to shale's constraints system)
Repeated low scores on a behavior auto-promote to a hard constraint.
Three sessions failing `consolidates` → auto-add a constraint
*"Before adding a node, search for similar existing concepts via
map_find_by_label"*. Self-tightening. Requires the constraints system
to exist in the agent (shale has it; vellum should adopt it).

### 4. Capability gating (interacts with `enforcement/`)
Low scores on responsible use of a tool temporarily revoke access.
Failed `surfaces_destructive` 5 times → `reference_set` requires a
paired `reference_get` in the same turn before executing. Tool-level
discipline. Implemented as enforcement-module rules driven by
scorecard signals.

### 5. Charter revision via failure examples
Low-scoring turns get appended to the charter as negative examples.
The charter document itself evolves. Highest automation, also highest
risk of pollution if the wrong examples land. Defer until #1-4 produce
clear patterns.

**Recommendation: build #1 + #2 first.** Transparency to the human,
context reminder to the agent. Both cheap, both work. #3 is the
natural next step (wires scorecard → constraints, both modules already
exist conceptually). #4 and #5 wait until real failure patterns are
visible.

The deeper truth worth naming explicitly: **"reinforcement" without
weights is iterative prompt design with a feedback loop.** The
scorecard isn't training the agent; it's training the human (or a
prompt-tuning agent) to make better prompts. Naming this honestly
keeps expectations calibrated.

## Files this plan creates

- `loom_agentic/scorecard/__init__.py`
- `loom_agentic/scorecard/charter.py` — load + validate charter YAML
- `loom_agentic/scorecard/runner.py` — post-hoc scoring entry point
- `loom_agentic/scorecard/self_score.py` — in-loop scoring helper
- `loom_agentic/scorecard/store.py` — score event persistence
- `loom_agentic/scorecard/judge_prompts.py` — prompt templates
- `charters/` directory at loom_agentic root, with example
  `charters/example_capture_agent.yaml`
- Tests covering charter parsing, score event shapes, judge prompt
  formatting

UI deferred to a separate plan when loom grows a UI surface.

## Implementation sequence

1. **This plan in writing** (now). Locks the design before drift.
2. **Charter loader + validator.** Read YAML, validate shape, tests.
3. **Score event shape + store.** Append-only via existing eventlog.
4. **Post-hoc runner.** Judge LLM evaluates transcript → score events.
   CLI invocation: `python -m loom_agentic.scorecard.runner --agent
   shale_capture --session <id>`. Manually score the Katrina-loop
   session in shale as the first real test.
5. **Self-score helper.** Agent in-loop: at end of each turn, agent
   reviews its own actions against charter, emits self-score event.
6. **Convert shale to use loom.** This is the long-deferred work the
   scorecard provides forcing function for. Done as its own plan
   (loom plan 3).
7. **In-context reminder.** Top-K low scores from prior sessions get
   prepended to the next session prompt. Lever #2 above.
8. **Constraint promotion.** Lever #3 above. Connects scorecard
   signals back into shale's existing constraints system.
9. **UI.** Once data exists. Separate plan.

## Options considered

- **Scorecards as a separate proving ground** vs as a loom module.
  Picked loom module. Scorecards are infrastructure that applies to
  ANY agent loom runs; making it a sibling module to `policy/` and
  `enforcement/` keeps the architectural story coherent. A separate
  proving ground would be appropriate if scoring became a
  user-facing product, but for now it's tooling.
- **Single shared charter** vs per-agent charters. Picked per-agent.
  Shale's capture agent and vellum's author agent have different
  purposes; one charter would either be too generic to score against
  or impose constraints inappropriate for one of them.
- **Score storage in dedicated DB** vs eventlog. Picked eventlog.
  Score events are events; they belong with the other agent events,
  reusing the same persistence and replay infra.
- **Hard constraint integration vs soft signal**. Picked soft by
  default, with explicit lever to promote to hard via constraint_set
  (lever #3). Scoring is observation; constraints are enforcement;
  promoting is an explicit step, not automatic until trust is earned.

## Open questions

- **Where do charters LIVE in the repo layout?** A `charters/`
  directory at loom root? Per-consumer-repo? Shale's charter for
  shale's capture agent could live in shale OR in loom. My instinct:
  per-consumer because the charter is the consumer's statement of
  intent for THAT agent, but the format/loader is loom's. Defer
  decision to implementation time.
- **Cost of judge-LLM scoring.** Cheap with Haiku (~$0.005 per
  session), but at scale this adds up. Per-session is fine; per-turn
  in-loop self-score adds latency to every turn. Worth measuring
  before defaulting it on.
- **Multi-criterion judge call vs per-criterion?** Single call is
  cheaper and lets the judge see the whole picture; per-criterion
  isolates each judgment but costs N× per session. Default to
  single-call with structured output (one judge prompt asks for all
  criteria scores at once).
- **What happens when the charter changes?** Old score events
  reference an old criteria taxonomy. Either snapshot the charter
  with each score event (storage cost) or version charters explicitly
  (`charters/shale_capture.v3.yaml`) and reference version. Defer.
- **Self-scoring honesty.** Will the agent score itself accurately,
  or just say "5 across the board"? Has to be tested empirically.
  The judge-LLM source is partly a check on this — when self and
  judge diverge significantly, that's a signal the self-scoring
  prompt needs sharpening or the criterion is gameable.

## Out of scope

- The UI itself (deferred plan)
- Loom's broader conversion of shale (loom plan 3)
- Vellum's adoption of loom (vellum plan 3 or later)
- Any actual model training or fine-tuning. Scorecards inform prompt
  iteration, not weight updates.
- Cross-agent comparison logic (interesting but premature; need single
  agent's scoring working first)
- Scorecard-to-charter feedback automation (lever #5; deferred)

## What this plan DOES NOT lock in

- The judge LLM choice (Haiku is the default; can swap)
- The exact criterion taxonomy (each charter defines its own; no
  global criterion set)
- The reinforcement levers beyond #1 and #2 (each is a separate
  decision when its trigger fires)
- The UI design (placeholder shape only)
- Whether scoring is sync or async (default: post-hoc async; toggle
  for in-loop self-score)

## Honest hedge

The whole reinforcement story rests on the assumption that an LLM
agent can usefully respond to its past scores in-context. This is
informed reasoning — LLMs do respond to "be careful about X" framing
— but the actual signal-to-noise ratio at scale is unknown. The first
real test is whether shale's capture agent scores measurably better
on `claims_match_reality` after a single in-context reminder is
added. If not, prompt design needs more work; the scorecard module
itself is still useful for transparency even if automated reinforcement
disappoints.
