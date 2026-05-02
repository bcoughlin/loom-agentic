# Spark — scorecards generate the training data

**Vision flash, captured before it evaporates.** Not actionable yet, may
never be in the form first imagined. The point is to preserve the
inspiration as written when it landed; future work can consult or ignore.

## The idea

The scorecard infrastructure designed in `vibeplan/20260501_plan_2`
isn't just a measurement system. It's also, **as a byproduct, a
training-data generator** for fine-tuning smaller open-source models
toward charter compliance.

Every session a scorecard evaluates produces preference signal. High-
scoring agent responses paired with low-scoring ones from the same
charter on the same criterion become exactly the (preferred, rejected)
pairs that DPO (Direct Preference Optimization) consumes for
preference tuning. No separate reward model needed; no RLHF complexity;
just paired comparisons that the scorecard naturally produces.

The framing shift: **the scorecard isn't a gate the agent passes
through, it's a dataset the agent emerges from.** Each scoring event
is a row in a future training set whether or not anyone ever fine-tunes
on it. Building the scorecard well — explicit charter, calibrated
rubrics, three score sources to triangulate — is the same work as
building good training data for a future fine-tune.

## What sparked the realization

Concrete instance: the user asked whether modest-budget weight-based
training is feasible for a small org. Real answer: yes, via LoRA /
QLoRA fine-tuning of 7-13B open bases (Llama 3, Mistral, Qwen, Gemma)
on rented A100s ($1-2/hour, $50-500 total per fine-tune), or DPO using
preference pairs. While answering, the connection landed: the
scorecard work in plan_2 IS the data-generation layer. Each scoreable
session emits the rows DPO needs, for free, as a side effect of the
measurement system already being designed.

## What's already in reach

Things any sufficiently-built scorecard system could enable today:

- **Per-criterion preference pair extraction.** Given two sessions
  scored against the same criterion (e.g. `consolidates`), where one
  scored high and one scored low, the agent's responses on those
  sessions are a preference pair for that criterion.
- **Judge model fine-tuning as the cheapest first win.** The
  scorecard's judge LLM is itself a narrow well-scoped task: read
  charter + transcript, output structured criterion scores. Fine-tune
  a 7B Qwen or Mistral specifically as a judge → 10-100× cheaper
  scoring at scale than calling Sonnet/Opus. Training data is
  human-corrected judge outputs (the human-source score events from
  plan_2's three-source design).
- **Agent specialization.** Once the judge is fine-tuned, the agent
  itself becomes a candidate. A LoRA adapter on a 13B base, trained
  on the high-scoring response patterns from the scorecard, becomes
  a charter-compliant specialist. Stays cheap to host (vLLM /
  Ollama / Together / Fireworks).
- **DPO without RLHF complexity.** Tooling exists: Hugging Face's
  TRL library, axolotl, unsloth wrappers. Compute envelope is the
  same as supervised fine-tuning.

## What's missing

- **Sufficient scoring volume.** A handful of sessions doesn't make a
  training set. Realistic threshold for DPO: 1000+ preference pairs
  per criterion to see meaningful tuning. That's 1000+ scored
  sessions, which is a real volume hurdle for a small project.
- **Calibration discipline.** Score events become training data ONLY
  if the rubrics are tight enough that scores mean the same thing
  across sessions. Loose rubrics produce noisy training data; noisy
  training data produces a worse model than no fine-tuning.
- **Domain-specificity.** A scorecard for shale's capture agent
  produces training data for a shale-capture-tuned model. Not
  transferable to vellum's author agent without a separate scorecard
  + dataset. This is fine, just bounds the win per-agent.
- **Human-in-the-loop overhead.** The "human" score source in plan_2
  is what calibrates the judge. Humans clicking through assessments
  to agree/disagree IS the calibration data; without it, the
  judge-LLM and self-score sources can drift together into
  consensual hallucination.

## Adjacent sparks

- **The scorecard becomes the agent's curriculum.** Instead of "fine-
  tune toward charter compliance," frame it as "fine-tune through
  the scorecard like a school curriculum." Early sessions score
  poorly because the agent is new; targeted fine-tuning on those
  failure patterns; later sessions score better; new failure patterns
  surface; iterate. The scorecard becomes the longitudinal record of
  the agent's progression.
- **Cross-agent transfer via shared rubrics.** Some criteria
  generalize: `claims_match_reality`, `surfaces_destructive`,
  `respects_authority`. A model fine-tuned on these criteria across
  multiple agents (shale capture + vellum author + future agents)
  might transfer better than per-agent specialists. Speculative.
- **The scorecard runner itself becomes the supervised teacher.**
  Today plan_2 has the judge LLM evaluating the agent. Tomorrow:
  judge LLM evaluates → if low score, judge generates the corrected
  response inline → that pair (agent's bad response, judge's
  corrected response) feeds the training set directly. Score AND
  generate training pairs in one pass.
- **Scorecards as a marketplace asset.** A well-calibrated scorecard
  for a domain (e.g. "good code review agent for Python") becomes a
  shareable artifact independent of any specific agent. Other
  developers fine-tune their agents against it; you publish the
  scorecard, they publish their tuned agent, the ecosystem
  reinforces the rubrics.
- **Reverse direction: training data without scorecards.** Existing
  good-quality agent transcripts could be retroactively scorecarded
  to extract preference pairs. The scorecard is the abstraction; the
  data can be extracted from anywhere that abstraction is applied.

## Open questions this spark doesn't answer

- **At what scoring volume does fine-tuning become net-positive?**
  Below some threshold the variance dominates and you ship a worse
  model. Empirical question; only one way to find out.
- **Is the judge-model fine-tune the right first target, or is the
  agent itself?** Judge is narrower (likely cheaper to win on); agent
  is the bigger ROI if it works (cheaper inference for the actual
  product surface). Probably do both, judge first.
- **Frontier-model floor.** Some agent tasks may genuinely need
  Sonnet/Opus-level reasoning and won't ever transfer to a 13B base.
  Need to identify which BEFORE committing to fine-tuning that task.
  Failure mode: spend $500 fine-tuning a 13B for a task only frontier
  models can do well.
- **The hosted-API side of fine-tuning.** OpenAI fine-tuning of
  GPT-4o-mini, Anthropic's enterprise fine-tuning. Easier than
  managing your own GPUs, you don't own the weights, costs more
  per-token. Worth comparing against open-source self-host on the
  specific use case before committing.

## The honest framing

This spark assumes scorecards reach scoring volume. They might not.
A small org running a couple agents on a couple domains might never
generate 1000+ scored sessions per criterion in any reasonable
timeframe. In that world, the scorecard's value is purely the
measurement / transparency / iterative-prompt-improvement loop
described in plan_2 — which is itself substantial. The training-data
byproduct is a *latent capability* that becomes real only at scale.

Even at low volume, the scorecard architecture COSTS NOTHING extra to
preserve the latent capability. Score events are stored either way;
the structured rubric exists either way; the human-judge calibration
happens either way. The training-data framing changes how you think
about WHAT to score and HOW to structure the rubrics (toward
preference-pair clarity), but doesn't add work to plan_2's
implementation.

The flash itself — *the scorecard IS the training data, scoring IS
data labeling* — stays valuable as a framing. Every measurement
system you build for an agent could double as the data pipeline for
training a successor. Once you see the symmetry, you can't unsee it.
The infrastructure decisions in plan_2 should be made with this
second use case in mind even if the first use case is the only one
that ever lands.

## Connection to other plans

- **`vibeplan/20260501_plan_2_scorecard_module`** — this spark is a
  derivative of plan_2's scorecard work. Plan_2 doesn't need to
  change to enable this spark, but the rubric design and storage
  shape decisions made in plan_2 directly affect how usable the
  resulting training data will be. Worth a brief note in plan_2 that
  "scoring rubrics should be tight enough that scores function as
  preference labels for future fine-tuning."
- **Reinforcement levers in plan_2** (#1 transparency, #2 in-context
  reminder, #3 constraint promotion, #4 capability gating, #5
  charter revision) — this spark adds a sixth lever: **#6
  preference-tune** the agent itself on the accumulated scorecard
  preference pairs. Strictly the most ambitious lever, requires the
  most volume, has the highest ceiling.
