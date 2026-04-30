# Plan 1 — Reasoning observability for loom_agentic

Two complementary observability layers that share architecture and ship together:

1. **Carry** — agent-emitted structured working state (deliberate, curated, cheap)
2. **Thinking capture** — provider-emitted reasoning traces (raw, expensive, optional)

Both are observability-only. Neither is injected back into the agent's prompt. Both must work with or without the other — loom should function fully when thinking is disabled, and thinking capture should function even if the agent never reports carry.

---

## Problem statement

Loom currently captures **position** (`report_position(node_id, rationale)`) — where the agent is on the chart, plus a per-turn rationale. That's two of three useful signals about agent reasoning. The other two:

- **Structured working state across turns** — working hypothesis, accumulated evidence with provenance, open obligations, ruled-out paths. Today: nowhere. Each turn the agent re-derives state from message replay.
- **Raw model deliberation** — the actual reasoning the model does before committing to a response or tool call. Today: discarded (when thinking is enabled at all). The `text` and `tool_use` blocks are the *output* of reasoning; thinking blocks are the *reasoning itself*.

Without these, replay shows the path and the agent's stated rationale but misses both the agent's tracked state and the model's actual deliberation. When the agent goes off-policy (canonical example: kepler asks user a question, then ignores the answer and starts a new detection loop), you can see the chart violation but not whether the model *considered* answering the question and decided against it, or never registered the user's reply as an answer at all. Three different failure modes, three different fixes.

---

## Design pivot — observability, NOT context

**Critical:** both carry and thinking are emitted to the event log for replay review. Neither is rendered back into the agent's prompt on subsequent turns.

Reasoning:
- Carry-as-context creates token cost, compaction problems, prompt-rendering complexity, and a class of "carry doesn't match what the agent believes" bugs
- Thinking-as-context is impossible by design — Anthropic requires thinking blocks be preserved across tool-use turns *as they were emitted*, not summarized back into a global state
- Observability is strictly additive — same model behavior as today, plus visibility
- Both sit at loom's observability tier (layers 2-3), NOT enforcement (layer 4)

What this means for the kepler conversational-drop bug:
- These layers will not *prevent* it
- They will *show* it clearly: replay will display the open obligation alongside the model's actual deliberation at the moment of the off-policy jump
- Structural prevention still belongs to per-node snippets + position reporting (plan 0 — kepler integration of existing loom). Observability informs which snippets need editing.

---

## Architecture

```
loom_agentic/
├── carry/                          ← NEW
│   ├── __init__.py
│   ├── schema.py                   ← carry slot dataclasses + validation
│   └── tests/
├── thinking/                       ← NEW
│   ├── __init__.py
│   ├── capture.py                  ← provider-agnostic thinking event shape
│   └── tests/
├── replay/
│   ├── stepper.py                  ← MODIFIED: tracks carry + thinking per frame
│   ├── static/
│   │   └── player.html             ← MODIFIED: expandable rails for both
│   └── ...
└── (no changes to enforcement.py, no prompt renderer changes, no policy loader changes)
```

Both layers feed the existing event log — same JSONL stream, new event types. The replay player surfaces them as separate UI elements that can be independently enabled, collapsed, or absent.

---

## Carry — agent-emitted structured state

### Schema (strawman v0)

```python
@dataclass
class Evidence:
    claim: str
    source: Literal["dino", "user", "tool", "llm_inference"]
    confidence: Optional[float] = None

@dataclass
class Obligation:
    kind: Literal["question", "deferred_decision", "pending_confirm"]
    text: str
    status: Literal["open", "answered", "abandoned"] = "open"

@dataclass
class CarryPatch:
    """Per-turn delta. Agent emits this; loom never accumulates back to the agent."""
    set_hypothesis: Optional[str] = None
    add_evidence: list[Evidence] = field(default_factory=list)
    open_obligation: Optional[Obligation] = None
    resolve_obligation: Optional[str] = None  # text-match against open ones
    rule_out: Optional[dict] = None  # {claim, reason}
    note: Optional[str] = None
```

The replay stepper accumulates patches into a per-frame snapshot for UI rendering. Agent never sees the snapshot.

### Tool surface

**Recommendation: extend `report_position(node_id, rationale, carry_patch=None)`.**

Most carry updates happen at decision points where position transitions happen anyway. One tool call per decision; rationale becomes the human-readable summary, carry_patch the structured version. No extra round-trip cost.

If the agent never emits a `carry_patch`, the system still works — replay just shows position + rationale, no carry rail. Carry is purely additive.

---

## Thinking capture — provider-emitted reasoning

### What this captures

When the calling code enables thinking on the LLM API (Anthropic `thinking` parameter, Gemini "thought summaries", etc.), the model emits reasoning content blocks distinct from `text` and `tool_use`. This plan defines a provider-agnostic event shape and routes those blocks into the event log.

```python
@dataclass
class ThinkingEvent:
    text: str                       # the raw thinking content (or summary)
    provider: str                   # "anthropic" | "google" | etc.
    turn: int
    position_node_id: Optional[str] # if the agent reported position this turn, link them
    token_count: Optional[int]      # for cost tracking
    truncated: bool = False         # true if budget cut off mid-deliberation
```

### Provider integration

**Anthropic Claude (kepler ClaudeDirector path):**
- Caller enables `thinking={"type": "enabled", "budget_tokens": N}` on `messages.create()`
- Response stream interleaves `thinking_delta` events with `text_delta` and `input_json_delta`
- Loom's event-log writer adds a `loom.thinking_capture(block)` helper called from the SSE handler whenever a thinking block completes
- Tool-use continuation: thinking blocks must be preserved verbatim in subsequent `messages` array entries per Anthropic's API contract — loom doesn't manage the message array (caller does), but DOCS.md will warn implementers

**Google Gemini (kepler GeminiDirector path):**
- Gemini 2.5 series "thought summaries" surface differently — typically a `thought` field on response parts
- `loom.thinking_capture` accepts the normalized `ThinkingEvent` shape; provider-specific extraction lives in caller code (kepler), not loom

**Other providers / no thinking enabled:**
- Loom never *requires* thinking events. If none arrive, replay omits the thinking rail. Zero-config degradation.

### Loom must work without thinking

Hard requirement, called out explicitly:
- All replay code paths handle `thinking_events == []` cleanly (no empty rail rendered, no console warnings)
- DOCS.md lists thinking as optional, with a "when to enable" section: high-stakes debugging, off-policy investigation, designing new flowchart nodes — NOT routine production monitoring (cost prohibitive)
- Tests assert that runs with no thinking events render correctly in player.html

---

## Replay UI extensions

The replay player gets two new rails next to the existing chart + rationale display:

**Carry rail** (right side, persistent):
- Shows accumulated carry state at current frame
- Slot diffs from previous frame highlighted (added evidence in green, closed obligations struck through)
- Stale obligation warning indicator (open >N turns) — visual flag for the reviewer
- Click obligation → jumps timeline to its open/close turns
- Hidden if no carry events in the run

**Thinking rail** (collapsible, default-collapsed):
- Per-frame disclosure widget — click to expand, see the raw thinking text for that turn
- Token count + truncation indicator visible in the collapsed header
- Hidden entirely if no thinking events in the run

Both rails are absent-by-default in UI when their event types are absent in the run — no empty rails, no "0 carry items" placeholders.

---

## Files to create / modify

**Create:**
- `loom_agentic/carry/__init__.py`
- `loom_agentic/carry/schema.py`
- `loom_agentic/carry/tests/test_schema.py`
- `loom_agentic/carry/tests/test_accumulator.py`
- `loom_agentic/thinking/__init__.py`
- `loom_agentic/thinking/capture.py` — `ThinkingEvent` dataclass + `capture(block)` helper that writes to event log
- `loom_agentic/thinking/tests/test_capture.py`

**Modify:**
- `loom_agentic/__init__.py` — re-export CarryPatch, Evidence, Obligation, ThinkingEvent
- `report_position` tool definition — add optional `carry_patch` arg
- `loom_agentic/replay/stepper.py` — Frame gains `carry_state`, `carry_diff`, `thinking_events`; add patch-fold + thinking-attach logic
- `loom_agentic/replay/static/player.html` — carry rail + thinking rail, both auto-hide when absent
- `DOCS.md` — author guide for carry slots; "when to enable thinking" section; tool-use-with-thinking gotchas
- `README.md` — concept table gains carry + thinking rows, both marked observability/optional

**No changes to:**
- `enforcement.py` (neither layer enforces anything)
- Policy loader / prompt renderer (nothing renders back to the agent)
- Orchestrate (both layers are replay-side)

---

## Step-by-step plan

1. Carry schema + validators + accumulator tests in isolation
2. Thinking capture event shape + writer tests in isolation
3. Extend `report_position` schema with optional `carry_patch`
4. Replay stepper changes — Frame gains carry + thinking fields; fold/attach logic; tests on fixture event log
5. Replay UI — carry rail + thinking rail, both with auto-hide when absent. Test on three fixture runs:
   - Run with neither carry nor thinking → only chart + rationale visible
   - Run with carry only → chart + rationale + carry rail
   - Run with both → chart + rationale + carry rail + thinking rail
6. Docs + examples
7. **Integration validation against kepler** (depends on plan 0 — kepler loom integration). Run a session that hits the conversational-drop bug:
   - With thinking disabled: verify carry shows the dropped obligation
   - With thinking enabled: verify the model's deliberation at the moment of the drop is visible
   - Compare what each layer reveals — informs whether thinking is worth its token cost for routine debugging or only for hard cases

---

## Options considered and recommendation

**A. Carry as observability vs context.** Observability. Decided.

**B. Combine carry + thinking in one plan vs split.** Combined (this plan). They share architecture (event log shape, stepper changes, UI rails), have the same observability-not-enforcement philosophy, and ship together.

**C. Tool surface for carry.** Extend `report_position`. Decided.

**D. Make thinking required.** No. Optional, gracefully absent. Cost prohibitive for routine use; valuable for debugging and node design.

**E. Provider-specific thinking adapters in loom.** No. `ThinkingEvent` is the normalized shape; per-provider extraction lives in caller code. Loom shouldn't carry SDK dependencies for every provider.

**F. Schema extensibility for carry.** Closed schema for v0. Reopen if real use cases emerge.

**G. Auto-extraction of carry from rationale or thinking.** No. Agent emits carry deliberately. If carry is tedious, the schema is wrong, not the mechanism.

---

## Out of scope

- Carry as prompt context (deliberately rejected)
- Carry compaction (not needed if it never re-enters the prompt)
- Stale-obligation enforcement
- Multi-agent shared carry
- Carry export / import for cross-session learning
- Visual diff playback (animation between frames)
- Auto-extraction of carry from any source
- Thinking-block summarization or filtering — capture verbatim or not at all
- Privacy / redaction of thinking blocks (proving-ground use; flag for production later)
- Provider-specific SDK adapters inside loom (callers handle extraction)

---

## Open questions

- **Tool surface decision** — recommendation is extending `report_position`, but worth a sanity check during implementation. If `report_position` calls become unwieldy with carry attached, split.
- **Patch granularity** — `add_evidence` accepts a list (multiple evidence items per turn) for cases where one tool call yields several observations. Trivial.
- **Thinking-block size limits in replay UI** — a 4000-token thinking block displayed inline could overwhelm the player. Recommend collapsed-by-default with token count in header, expand on click. Maybe a "first 200 chars + …" preview in collapsed state.
- **Linking thinking to position** — if the model emits thinking, then `report_position`, then more thinking, then a tool call, do we attach the thinking to the position transition or render as a sequence? Recommend sequence with timestamps; replay UI groups them per turn but preserves order.
- **Verification path for thinking API contract** — read [docs.anthropic.com extended thinking](https://docs.anthropic.com/en/docs/build-with-claude/extended-thinking) for current API shape, especially the tool-use-with-thinking constraints (recently tightened). Update DOCS.md based on what's there at implementation time, not what I remember.
- **Gemini thought summary surface** — verify against current `google-genai` SDK docs. Less detailed than Claude's thinking; may need a "low-fidelity" badge in the UI when source is Gemini to set reviewer expectations.
- **Cost reporting** — should the replay player show total thinking-token cost for the session? Useful for "is this debug session worth it" decisions. Trivial to add; defer to v0.1.
