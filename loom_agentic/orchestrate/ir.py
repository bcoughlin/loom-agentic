"""Intermediate representation (IR) for Loom Orchestrate.

Parser emits IR; builder consumes it. Keeping the two sides apart via a
stable IR means we can later swap the frontend (TOML-only spec, UI-emitted
JSON, etc.) without rewriting the LangGraph builder.

The IR captures only what LangGraph cares about at build time:
- nodes with types (function vs conditional router)
- edges with optional labels (labels turn a set of outgoing edges into a
  conditional_edges router)
- explicit start and end nodes

Runtime data (context carry, TOML sidecar payloads) is out of scope for
Orchestrate v0 — that lives in the Plugin/downstream path.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

NodeType = Literal["function", "conditional", "start", "end"]


@dataclass(frozen=True)
class Node:
    """A graph node — maps to an `add_node(id, fn)` or a conditional router."""
    id:    str
    label: str
    type:  NodeType

    def is_routable(self) -> bool:
        """Nodes that need a callable in the registry (function or conditional)."""
        return self.type in ("function", "conditional")


@dataclass(frozen=True)
class Edge:
    """A graph edge. `label` is the routing key for conditional edges.

    When the source is a conditional node (diamond), `label` is the value the
    router returns to pick this outgoing edge. For plain function nodes,
    `label` is ignored (set to None).
    """
    source: str
    target: str
    label:  str | None = None


@dataclass
class Graph:
    """The IR for a Loom-orchestrated LangGraph.

    Invariants (checked in `validate()`):
    - exactly one `start` node exists and is referenced as `start_id`
    - exactly one `end` node exists and is referenced as `end_id`
    - every edge's source and target point to known nodes
    - conditional nodes have >= 2 outgoing edges, all labeled
    - function nodes have exactly one outgoing edge (unlabeled) OR are the
      source of a labeled edge set that behaves like a router
    """
    nodes:    dict[str, Node]
    edges:    list[Edge]
    start_id: str
    end_id:   str
    # Preserves any non-node lines from the source (e.g. Mermaid directives)
    # so round-tripping back to text is stable. Not used during build.
    directives: list[str] = field(default_factory=list)

    # ────────────────────────────────────────────────────────────────────
    # Queries
    # ────────────────────────────────────────────────────────────────────

    def outgoing(self, node_id: str) -> list[Edge]:
        return [e for e in self.edges if e.source == node_id]

    def incoming(self, node_id: str) -> list[Edge]:
        return [e for e in self.edges if e.target == node_id]

    def function_nodes(self) -> list[Node]:
        return [n for n in self.nodes.values() if n.type == "function"]

    def conditional_nodes(self) -> list[Node]:
        return [n for n in self.nodes.values() if n.type == "conditional"]

    # ────────────────────────────────────────────────────────────────────
    # Validation
    # ────────────────────────────────────────────────────────────────────

    def validate(self) -> None:
        """Raise ValueError describing any invariant violation."""
        if self.start_id not in self.nodes:
            raise ValueError(f"start_id '{self.start_id}' is not a known node")
        if self.end_id not in self.nodes:
            raise ValueError(f"end_id '{self.end_id}' is not a known node")
        if self.nodes[self.start_id].type != "start":
            raise ValueError(f"start node '{self.start_id}' must be type 'start'")
        if self.nodes[self.end_id].type != "end":
            raise ValueError(f"end node '{self.end_id}' must be type 'end'")

        for edge in self.edges:
            if edge.source not in self.nodes:
                raise ValueError(f"edge source '{edge.source}' is unknown")
            if edge.target not in self.nodes:
                raise ValueError(f"edge target '{edge.target}' is unknown")

        for node in self.conditional_nodes():
            out = self.outgoing(node.id)
            if len(out) < 2:
                raise ValueError(
                    f"conditional node '{node.id}' needs >= 2 outgoing edges "
                    f"(got {len(out)})"
                )
            missing = [e for e in out if not e.label]
            if missing:
                raise ValueError(
                    f"conditional node '{node.id}' has unlabeled outgoing edge(s) "
                    f"to {[e.target for e in missing]} — label them with |...|"
                )

        # Every non-end node must have at least one outgoing edge (otherwise
        # the graph has a dead end other than END).
        for node in self.nodes.values():
            if node.type == "end":
                continue
            if not self.outgoing(node.id):
                raise ValueError(
                    f"node '{node.id}' has no outgoing edges and is not the end"
                )
