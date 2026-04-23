"""Build a compiled LangGraph from IR + a function registry.

The registry is a plain dict mapping node id -> callable:
  - Function nodes:    fn(state) -> state_update (dict)
  - Conditional nodes: fn(state) -> str (one of the outgoing edge labels)

START and END nodes don't need entries; they map to langgraph's builtins.

Missing registry entries for routable nodes raise at build time with a clear
message — we prefer failing fast over silent-skip behavior that would
produce a graph that hangs at runtime.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from langgraph.graph import END, START, StateGraph

from .ir import Graph, Node

Registry = dict[str, Callable[..., Any]]


class RegistryError(ValueError):
    pass


def build_from_mermaid(
    mermaid_source: str,
    registry: Registry,
    state_schema: type,
    *,
    checkpointer=None,
):
    """Convenience: parse Mermaid -> IR -> compiled LangGraph app."""
    from .mermaid_parser import parse_mermaid
    graph = parse_mermaid(mermaid_source)
    return build_from_ir(graph, registry, state_schema, checkpointer=checkpointer)


def build_from_ir(
    ir: Graph,
    registry: Registry,
    state_schema: type,
    *,
    checkpointer=None,
):
    """Compile an IR Graph into a LangGraph `app` using the given registry.

    Args:
        ir:           The parsed/validated Loom IR.
        registry:     Maps node id -> callable. Function nodes receive state
                      and return state updates. Conditional nodes receive
                      state and return the edge label to follow.
        state_schema: A TypedDict class describing the graph state.
        checkpointer: Optional LangGraph checkpointer; passed to `compile()`.

    Raises:
        RegistryError: if any routable node lacks a registry entry.
    """
    ir.validate()
    _require_registry_coverage(ir, registry)

    builder = StateGraph(state_schema)

    # Register function and conditional nodes. START/END are builtins; we
    # map them via edge-level references, not as named nodes.
    #
    # Conditional nodes are modeled in LangGraph as a node + a separate
    # `add_conditional_edges` call on its outgoing side. The node itself
    # is a passthrough (returns empty state update); the routing function
    # (from the registry) is wired via add_conditional_edges below.
    for node in ir.nodes.values():
        if node.type == "function":
            builder.add_node(node.id, registry[node.id])
        elif node.type == "conditional":
            builder.add_node(node.id, _passthrough)

    # Entry edge: START -> first node after the IR's start_id
    first = _single_successor(ir, ir.start_id, "start")
    builder.add_edge(START, first)

    # Terminal edge: node preceding the IR's end_id -> END
    # (we handle this via per-edge emission below — outgoing edges whose
    #  target is the end_id become edges to END.)

    # Wire function-node outgoing edges and conditional routers
    for node in ir.nodes.values():
        if node.type == "start":
            continue  # handled via the START -> first edge above
        if node.type == "end":
            continue  # END is a terminal sink; no outgoing

        outgoing = ir.outgoing(node.id)

        if node.type == "function":
            if len(outgoing) == 1:
                edge = outgoing[0]
                target = END if edge.target == ir.end_id else edge.target
                builder.add_edge(node.id, target)
            else:
                # A function node with multiple outgoing edges — same shape
                # as a conditional, but no explicit router. We require the
                # registry to supply a router under the same node id, OR the
                # edges to be labeled with the router's return value.
                if not all(e.label for e in outgoing):
                    raise RegistryError(
                        f"function node '{node.id}' has {len(outgoing)} outgoing "
                        f"edges but no labels — add |...| labels or reduce to one"
                    )
                raise RegistryError(
                    f"function node '{node.id}' has multiple outgoing edges — "
                    f"change it to a diamond `{{...}}` so Loom treats it as a "
                    f"conditional router"
                )

        elif node.type == "conditional":
            path_map: dict[str, str] = {}
            for edge in outgoing:
                target = END if edge.target == ir.end_id else edge.target
                path_map[edge.label] = target
            # registry[node.id] is the router callable returning an edge label
            builder.add_conditional_edges(node.id, registry[node.id], path_map)

    return builder.compile(checkpointer=checkpointer)


# ───────────────────────────────────────────────────────────────────────────
# Helpers
# ───────────────────────────────────────────────────────────────────────────

def _require_registry_coverage(ir: Graph, registry: Registry) -> None:
    missing = [
        node.id for node in ir.nodes.values()
        if node.is_routable() and node.id not in registry
    ]
    if missing:
        raise RegistryError(
            f"registry is missing entries for {missing}. "
            f"Every function and conditional node needs a callable."
        )


def _single_successor(ir: Graph, node_id: str, kind: str) -> str:
    out = ir.outgoing(node_id)
    if len(out) != 1:
        raise ValueError(
            f"{kind} node '{node_id}' must have exactly one outgoing edge "
            f"(got {len(out)})"
        )
    return out[0].target


def _passthrough(state: dict) -> dict:
    """Empty state update for conditional nodes. The routing happens in
    the add_conditional_edges call on this node's outgoing side; the node
    itself has no work to do.
    """
    return {}
