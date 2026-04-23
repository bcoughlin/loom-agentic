# Loom Agentic

Loom is a thin layer on top of [LangGraph](https://github.com/langchain-ai/langgraph) that treats the agent's
**behavioral policy as an authored Mermaid flowchart**, renders that
flowchart into the system prompt, and grades actual runs against it.

It is not a graph-compilation framework. The LangGraph graph stays a
fixed ReAct topology (`agent -> tools -> agent -> end`). The flowchart
lives at the *prompt* layer — Claude reads it and names its current
position every turn via a `report_position` tool. Loom's replay UI
renders the authored flowchart with the agent's actual path overlaid in
color, so the "design" and the "reality" share one source of truth.

See [DOCS.md](DOCS.md) for the authoring guide.

---

## Repository layout

```
loom_agentic/
├── __init__.py       ← module metadata
├── enforcement.py    ← layer-4 enforcement primitives
├── orchestrate/      ← Path B (Mermaid → StateGraph compiler)
│   ├── ir.py         ← intermediate representation
│   ├── mermaid_parser.py ← Mermaid flowchart → IR
│   ├── graph_builder.py  ← IR → compiled LangGraph app
│   └── tests/
└── replay/           ← event-log → frames + mermaid synthesis
    ├── __init__.py   ← serialize_run / serialize_run_listing
    ├── loader.py     ← load JSONL from S3 or disk, group by invocation
    ├── stepper.py    ← events → Frame list (what to highlight per tick)
    ├── mermaid_for_run.py ← synthesize ReAct mermaid from events
    ├── static/
    │   └── player.html    ← self-contained HTML replay viewer
    └── tests/
```

---

## Installation

```bash
pip install loom-agentic
```

Optional dependencies:

```bash
pip install loom-agentic[orchestrate]   # adds langgraph
pip install loom-agentic[replay-s3]     # adds boto3 for S3 event loading
```

---

## Concepts at a glance

| Piece | Role |
|---|---|
| **`<agent>.policy.mmd`** | The flowchart. What Claude sees and what the admin renders. |
| **`<agent>.policy.yaml`** | Per-node / per-edge prompt snippets + globals + version. |
| **Policy loader** | Assembles the `.mmd` + `.yaml` into a system prompt section. |
| **`report_position` tool** | Required parallel tool call on every tool-using turn. Args: `node_id`, `rationale`. |
| **Event log** | JSONL stream written by your tracing wrapper (e.g. `traced_ainvoke`). |
| **Replay** | `loom_agentic.replay` — event log → frames + mermaid, consumed by `player.html`. |
| **Policy-update barrier** | On resumed threads whose prior sha differs from current, injects a reminder message + emits `on_policy_update` event. |

---

## Quick start — Orchestrate

Build a LangGraph app from a Mermaid flowchart:

```python
from loom_agentic.orchestrate import build_from_mermaid

MERMAID = """
flowchart TD
    START([start]) --> classify
    classify[Classify input]
    classify --> route{needs_tool?}
    route -->|yes| tool
    route -->|no| reply
    tool[Run tool] --> reply
    reply[Generate reply] --> END([end])
"""

registry = {
    "classify": classify_fn,
    "route":    lambda s: "yes" if s["needs_tool"] else "no",
    "tool":     tool_fn,
    "reply":    reply_fn,
}

app = build_from_mermaid(MERMAID, registry, MyState)
result = app.invoke({"input": "hello"})
```

---

## Quick start — Replay

Load events and generate replay frames:

```python
from loom_agentic.replay import load_events, group_by_run, frames_for_run, mermaid_for_run, serialize_run

# From a local JSONL file
events = load_events("logs/2026-04-17.jsonl")

# Or from S3 (requires boto3)
events = load_events("s3://your-bucket/logs/agents/2026/04/17/")

runs = group_by_run(events)
for run in runs[:5]:
    payload = serialize_run(run)
    # payload is JSON-ready for player.html
```

Open `loom_agentic/replay/static/player.html` in a browser and drag-drop
the JSON, or inject it via `window.LOOM_RUN_JSON`.

---

## The four-section runtime prompt

Every turn, the policy loader produces:

1. **Invariants** — `globals:` from the YAML, rendered above the flowchart as "apply at every node" rules.
2. **Mermaid** — the `.policy.mmd` injected verbatim inside a fenced block, with version + sha stamp.
3. **Per-node and per-edge snippets** — each `nodes[id].prompt` / `edges[src->dst].prompt` rendered with a section header.
4. **Position-reporting contract** — explicit list of allowed node ids, with `report_position(node_id, rationale)` required as a parallel call whenever any other tool fires.

---

## Policy-update barrier

When a thread resumes under a newer policy than its last turn ran
under, Loom injects a synthetic `HumanMessage` at the head of the
current state:

> `[policy update] This thread was previously running under
> my_agent@v2 (sha 180cdc02). The policy has changed to
> my_agent@v3 (sha abc12345). The invariants and flowchart in
> your current system prompt take precedence over any patterns from
> your earlier turns on this thread. Re-read the invariants, then
> proceed.`

An `on_policy_update` event is also written to the event log, which
`stepper.py` renders as a barrier frame in the replay. This makes policy
iteration safe on active threads instead of silently losing to prior
anchoring.

Sha is computed over the `.policy.mmd` contents. Pure YAML-only edits
(adding a snippet, clarifying a `when:`) do NOT trigger the barrier
— only structural changes to the flowchart do.

---

## How to run Loom in a new agent

1. Author `<agent>.policy.mmd` + `<agent>.policy.yaml` alongside your
   agent handler.
2. At cold start, load the policy:
   ```python
   from your_policy_loader import load_policy
   _POLICY = load_policy("my_agent",
       search_dirs=[os.path.join(HANDLER_DIR, "prompts")])
   ```
3. Append `_POLICY.render_prompt_section()` to the agent's system prompt.
4. Add a `report_position(node_id, rationale)` tool (enforces the
   closed-vocabulary `node_id` and requires `rationale`).
5. Pass `policy_version=_POLICY.version, policy_sha=_POLICY.sha` to
   your tracing wrapper so the barrier mechanism works on resumed threads.

The replay then shows:

- The authored Mermaid with the agent's actual path highlighted
  (green = reported, yellow = inferred, red = off-policy)
- A rationale bubble anchored to the current position
- Click-to-snippet on any node to inspect the authored prompt
- A barrier marker at any policy-update crossed during the run

---

## Enforcement layers — when prompt rules lose

Loom assumes authored policy will be ignored sometimes — Claude's
training biases can out-compete any individual prompt rule under
pressure. The response isn't to shout louder in the prompt; it's to
add more layers so no single layer is load-bearing alone.

| # | Layer | Mechanism | When it works |
|---|---|---|---|
| 1 | Prompt-level policy | Mermaid + invariants + snippets rendered via `render_prompt_section` | Default case. Claude reads, Claude obeys. |
| 2 | Position reporting | `report_position(node_id, rationale)` required on tool-using turns | Always. Makes deviation visible at replay time. |
| 3 | Rationale audit | `rationale` required arg, rendered as a bubble on the chart | Always. The agent's stated "why" exposes anti-patterns. |
| 4 | Tool-layer rejection | `loom_agentic.enforcement` primitives return error strings to the model | When layers 1-3 diagnose a bug that prompt edits can't fix. |

```python
from loom_agentic.enforcement import reject_packed_dict

@tool
def apply_correction(path: str, value: Any, note: str = '') -> str:
    """Update ONE player-confirmed progress fact. Scalar only."""
    err = reject_packed_dict('apply_correction', value)
    if err: return err
    return _call('apply_correction', {'path': path, 'value': value, 'note': note})
```

---

## License

MIT
