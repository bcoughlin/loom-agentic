# Spark — internal vs external channels

**Vision flash, captured before it evaporates.** Not actionable yet, may
never be in full form. The point is to preserve the inspiration as
written when it landed; future work can consult or ignore.

## The idea

Every agent's output today is treated as ONE channel — whatever it
emits goes to the user. But there are at least two distinct kinds of
output that should be separated by design:

- **External**: what the user actually needs to act on or read —
  answers, questions, requests for input, error reports requiring
  their attention.
- **Internal**: feedback the agent generates for ITSELF — process
  narration, reasoning about its own tool calls, reading-its-own-
  warnings-aloud, defensive justifications.

The blurriness is the failure mode. Today's agents constantly leak
internal narration into the external channel because there's only
one channel to write to. Result: the user reads agent monologue
about its own tool-call hygiene that they didn't ask for and don't
care about.

## What sparked the realization

Concrete instance: in shale this session, after a `reference_set`
returned `change: OVERWROTE existing reference X.Y`, the agent's
next reply opened with *"That was an intentional overwrite — I
fetched the prior table mentally and merged all known data points
into it."* The user had said "75 is 218,800" and asked nothing else.
Agent had read its own tool-result warning and felt compelled to
defend itself in the chat reply.

The change-status feedback (designed to make the agent self-correct
on unintentional overwrites) was working too well in the wrong
direction — agent was treating ALL warnings as things the user
needs to know about. The user named the issue precisely: *"why does
agent say 'That was an intentional overwrite...' like it's
responding to itself? i didn't question anything."*

Then named the principle: *"maybe prompts need a 'internal' versus
'external' guardrail generally."*

## Why the framing matters

This isn't a shale-specific bug. It's a general design dimension
that applies to any agent with tool access:

- **Vellum's Author agent**: the reasoning behind a proposed bible
  section ("I'm proposing this because clusters X, Y, Z reached
  density threshold...") should land in proposal provenance — not
  in the chat with the human reviewer.
- **Loom's scorecard self-score**: the agent's evaluation of its
  own work is internal feedback. Echoing it back to the user as
  "I think I did well on `claims_match_reality`" is noise.
- **Any agent doing tool-use loops**: the `read tool, decide what
  to do, do it` cycle has internal reasoning at each step. Almost
  none of it belongs in the user-facing reply.

Once you see the dimension, you see it in every agent product.

## Three levels of implementation

Increasing cost, increasing rigor:

### Level 1 — Prompt-level guardrail

Add a SYSTEM_PROMPT section establishing the principle. *"Tool
results are internal feedback. Don't echo them in your reply unless
the user asked OR something genuinely needs their attention.
Process narration belongs internally, not in chat. Default: internal
stays internal."* Plus 3-4 concrete examples of internal-leaking-
external from real failure modes.

- **Cost**: zero code, ~10 minutes prompt edit
- **Risk**: relies on the agent honoring the line; LLM compliance
  with prompt rules is uneven under pressure
- **Best for**: starting point, validates the principle is real
  before paying architecture cost

### Level 2 — Tool-result tagging

Every tool result field carries explicit visibility metadata:
`audit: "OVERWROTE..."` (internal-only) vs `user_warn: "data lost"`
(external-required). Agent prompted to handle them differently.
Result shape becomes:

```json
{
  "ok": true,
  "summary": "...",
  "audit": "OVERWROTE existing reference X.Y",
  "user_warn": null
}
```

- **Cost**: per-tool-result schema change, prompt update
- **Benefit**: clearer separation, less reliance on prompt discipline
- **Risk**: still requires the agent to respect the visibility tags
  in its reply composition

### Level 3 — Architectural channels

Agent's output is structured into multiple lanes by design, not by
prompt:

- `reasoning` — internal, logged for audit, never shown
- `user_reply` — external, shown in chat
- `audit` — internal, persisted for review/scoring

Agent emits structured output (tool call OR multi-field content
block). UI renders only `user_reply`. Internal lanes flow to the
event log.

- **Cost**: tool definition rewrite, UI rewrite, prompt rewrite
- **Benefit**: structurally impossible to leak; the agent CAN'T
  put internal narration in external because the channels are
  physically separate
- **Risk**: meaningful design surface; some agent products do this
  (Anthropic's extended thinking is conceptually similar — separate
  channel for reasoning)

## What's already in reach

- Loom's eventlog already has the substrate to log internal
  channels separately. Today everything goes to the same log; the
  consumer (replay UI, scorecard runner) doesn't distinguish
  "audit-internal" from "user-facing." Could.
- Loom's policy/charter system could grow a "channel discipline"
  criterion — score whether the agent kept internal stuff out of
  user-facing replies. Direct fit for the scorecard module
  (`vibeplan/20260501_plan_2_scorecard_module`).
- Anthropic's extended thinking (when used) is already a separated
  internal channel for reasoning. Provides existence proof that the
  pattern works at the model layer.

## What's missing

- **Empirical data on whether prompt-level (level 1) is enough.**
  Won't know until it's running for a while. The shale prompt edit
  this session is the first test.
- **A clean tool-result schema for level 2.** Field naming matters
  — `audit` and `user_warn` are reasonable but probably not optimal
  on second pass.
- **A model for "the user's question implicitly asks about the
  agent's reasoning."** Sometimes the user IS asking "why did you
  do that?" In those cases, internal becomes external on demand.
  The default is internal-stays-internal; the exception is
  user-explicit-question. The agent has to detect this exception
  reliably.
- **Cross-channel consistency.** If the user-facing reply says
  one thing and the audit log says another, that's a worse failure
  than today's noisy unified channel. Channels need to be
  consistent in substance even when separated in surface.

## Adjacent sparks

- **The "internal vs external" dimension applies to TIME too.**
  What's internal in this turn might be external next turn (the
  agent reasons internally now, summarizes externally later when
  asked). A "deferred external" channel — internal until summoned —
  could carry rich provenance the user can dig into when curious.
- **Agent-to-agent communication.** A judge LLM evaluating a
  subject agent reads the subject's transcript. Today the subject's
  internal-leaked-external content pollutes the judge's view. With
  channel separation, the judge could read the dedicated
  reasoning/audit channel instead of the user-facing chat —
  cleaner, more accurate.
- **The user IS another agent in the multi-agent case.** "Internal"
  vs "external" is really "this agent" vs "downstream consumer."
  Generalizes to any agent topology.
- **Confidence calibration.** Internal channel could carry the
  agent's confidence in each claim; external channel only surfaces
  high-confidence claims by default. Low-confidence claims get
  flagged with hedging words OR move into "open questions" at the
  end of the reply.

## Open questions this spark doesn't answer

- **Is level 1 (prompt-only) enough in practice?** Empirical
  question. The shale prompt edit is the first data point.
- **Does the channel separation help the user, or just produce
  cleaner-looking output that hides important signals?** The
  agent's defensive "I fetched first" reply was annoying, but it
  also surfaced that the agent had thought about the overwrite. If
  that signal moves to internal, does the user lose useful insight
  into the agent's behavior?
- **How does this interact with audit/scorecard?** If reasoning
  lives in an internal channel, the scorecard can score it (better,
  it's structured). If it leaks into user-facing replies, scoring
  has to disentangle. Cleaner is better for evaluability.
- **What about acknowledging mistakes?** When user catches the
  agent in something wrong, the acknowledgment IS external — user
  needs to see it. But the agent's analysis of *why* it made the
  mistake is internal. The line between "acknowledge" and "explain"
  matters.

## Honest hedge

This framing is sharp but unproven. The level-1 prompt edit just
landed in shale; we don't know yet whether prompt-only enforcement
holds. If it doesn't, the question is whether to escalate to level
2 (tool-result tagging) or accept that some leakage is inherent to
LLM agents and design around it elsewhere (e.g. the UI hides certain
patterns, or post-processing strips them).

The cost of getting this wrong is mostly tone — agents either
sound defensively chatty (current state) or coldly mechanical
(over-correcting). Neither is fatal. But getting it RIGHT — agent
that says exactly what the user needs and nothing more, with full
internal richness preserved for audit — is a meaningful product
quality dimension that today's agents mostly fail at.

## Connection to other plans

- **`vibeplan/20260501_plan_2_scorecard_module`** — channel
  discipline becomes a natural scoreable criterion: *"Did the
  agent's user-facing reply contain internal narration that wasn't
  asked for?"* Easy rubric: count internal-leak phrases ("I'll
  fetch...", "I noticed the warning...", "That was intentional
  because..."). Deduct per occurrence.
- **`vibeplan/20260501_plan_3_web_module`** — if level 3 ever
  lands, the LoomPlayer could show the internal channels in a
  separate inspectable panel ("show reasoning") that's collapsed
  by default. Same UI pattern as code editors hide minimap by
  default.
- **`vibespark/20260501_spark_1_scorecards_as_training_data`** — a
  charter criterion for channel discipline becomes preference-pair
  training data once enough scoring volume exists. Fine-tune
  toward replies that respect the internal/external boundary.
- **`vibespark/20260501_spark_2_mutation_as_embedding`** (in shale's
  vibespark dir) — the elevation primitive there is internal by
  nature; only the elevated artifact (fact, prose) is external. The
  internal/external distinction is implicit in the elevation idea
  but worth making explicit.
