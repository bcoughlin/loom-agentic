"""Loom Orchestrate — build LangGraph apps from Mermaid blueprints.

Public API:
    from loom_agentic.orchestrate import build_from_mermaid, build_from_ir
    from loom_agentic.orchestrate.ir import Graph, Node, Edge
    from loom_agentic.orchestrate.mermaid_parser import parse_mermaid

Example:
    MERMAID = '''
    flowchart TD
        START([start]) --> classify
        classify[Classify input]
        classify --> route{needs_tool?}
        route -->|yes| tool
        route -->|no| reply
        tool[Run tool] --> reply
        reply[Generate reply] --> END([end])
    '''

    registry = {
        "classify": classify_fn,          # state -> {"intent": ...}
        "route":    lambda s: "yes" if s["needs_tool"] else "no",
        "tool":     tool_fn,
        "reply":    reply_fn,
    }

    app = build_from_mermaid(MERMAID, registry, MyState)
    result = app.invoke({"input": "hello"})
"""

from .graph_builder import RegistryError, build_from_ir, build_from_mermaid
from .ir import Edge, Graph, Node
from .mermaid_parser import MermaidParseError, parse_mermaid

__all__ = [
    "Edge",
    "Graph",
    "MermaidParseError",
    "Node",
    "RegistryError",
    "build_from_ir",
    "build_from_mermaid",
    "parse_mermaid",
]
