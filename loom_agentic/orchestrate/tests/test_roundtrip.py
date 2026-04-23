"""End-to-end Orchestrate test: Mermaid -> IR -> LangGraph -> run.

Exercises every v0 feature:
  - header parsing (`flowchart TD`)
  - start/end stadium nodes with reserved ids
  - function nodes (rectangles)
  - conditional node (diamond) with labeled edges
  - registry-backed routing
  - a full invoke that flows through both branches across two runs

Run:  python -m pytest loom_agentic/orchestrate/tests/test_roundtrip.py -v
Or:   python loom_agentic/orchestrate/tests/test_roundtrip.py  (smoke test)
"""

from __future__ import annotations

from typing import TypedDict

from loom_agentic.orchestrate import build_from_mermaid


MERMAID = """
flowchart TD
    START([start]) --> classify
    classify[Classify input]
    classify --> gate{wants_upper?}
    gate -->|yes| shout
    gate -->|no| whisper
    shout[Shout reply]
    whisper[Whisper reply]
    shout --> END([end])
    whisper --> END
"""


class State(TypedDict, total=False):
    input:   str
    upper:   bool
    reply:   str


def classify(state: State) -> dict:
    """Function node: looks at `input`, sets `upper` based on presence of '!'."""
    return {"upper": "!" in state["input"]}


def gate_router(state: State) -> str:
    """Conditional node: picks the `yes` or `no` outgoing edge."""
    return "yes" if state["upper"] else "no"


def shout(state: State) -> dict:
    return {"reply": state["input"].upper()}


def whisper(state: State) -> dict:
    return {"reply": state["input"].lower()}


REGISTRY = {
    "classify": classify,
    "gate":     gate_router,
    "shout":    shout,
    "whisper":  whisper,
}


def test_mermaid_orchestrate_roundtrip():
    app = build_from_mermaid(MERMAID, REGISTRY, State)

    loud = app.invoke({"input": "hello!"})
    assert loud["reply"] == "HELLO!", loud

    soft = app.invoke({"input": "hello"})
    assert soft["reply"] == "hello", soft


def test_mermaid_structure_exposed():
    """The compiled graph should expose the Mermaid we can inspect."""
    app = build_from_mermaid(MERMAID, REGISTRY, State)
    rendered = app.get_graph().draw_mermaid()
    # Sanity: the node ids we declared made it through to the compiled graph.
    assert "classify" in rendered
    assert "gate" in rendered
    assert "shout" in rendered
    assert "whisper" in rendered


if __name__ == "__main__":
    test_mermaid_orchestrate_roundtrip()
    test_mermaid_structure_exposed()
    print("Orchestrate roundtrip OK")
    print()
    # Print the compiled graph's own Mermaid to show what LangGraph sees
    app = build_from_mermaid(MERMAID, REGISTRY, State)
    print("Compiled graph structure (via LangGraph):\n")
    print(app.get_graph().draw_mermaid())
