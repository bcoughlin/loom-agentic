"""Parse a Mermaid flowchart into Loom IR.

Supported subset (v0):
  - `flowchart TD` / `flowchart LR` / `graph TD` / `graph LR` header
  - Comments (`%% ...`)
  - Node shapes:
      A[Label]      -> function node
      A{Label}      -> conditional (diamond, routes by edge label)
      A([Label])    -> start/end stadium (reserved IDs: START / END)
  - Edges:
      A --> B
      A -->|label| B    (labeled edge, typically used after diamond source)
  - Node shorthand: if a node appears only in an edge without a separate
    declaration, we create a function node with the ID as both id and label.

Unsupported (will parse but silently ignore or raise):
  - Subgraphs
  - CSS class defs / click handlers
  - Multi-line labels, HTML in labels
  - Non-flowchart diagrams (sequence, state, gantt, ...)

The parser is deliberately forgiving where it can be and strict where it
must be — malformed shape syntax raises; unknown directives warn only.
"""

from __future__ import annotations

import re
from typing import Iterable

from .ir import Edge, Graph, Node

# Reserved IDs that opt into START / END regardless of Mermaid shape
_RESERVED_START = {"START", "__start__", "start"}
_RESERVED_END   = {"END", "__end__", "end"}

# Node declarations:
#   A[Label]            function
#   A{Label}            conditional
#   A([Label])          stadium (used for start/end)
# ID is alnum + underscore. Label captures everything inside the brackets.
_RE_RECT    = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\[(.*?)\]$")
_RE_DIAMOND = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\{(.*?)\}$")
_RE_STADIUM = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\((?:\((.*?)\)|(.*?))\)$")

# Edge lines — we match on the arrow first, then parse each endpoint, which
# may itself be a shape declaration or a bare id. Labels are `|...|` between
# the arrow parts.
_RE_EDGE = re.compile(
    r"^(?P<src>.+?)\s*-->(?:\s*\|(?P<label>[^|]+?)\|)?\s*(?P<dst>.+?)$"
)

_RE_HEADER = re.compile(r"^(?:flowchart|graph)\s+(?:TD|LR|TB|BT|RL)\s*$", re.IGNORECASE)


class MermaidParseError(ValueError):
    pass


def parse_mermaid(source: str) -> Graph:
    """Parse a Mermaid flowchart string and return the IR.

    Raises MermaidParseError on unrecoverable syntax; emits validated IR
    (calls `graph.validate()` before returning).
    """
    nodes:      dict[str, Node] = {}
    edges:      list[Edge]      = []
    directives: list[str]       = []
    start_id:   str | None      = None
    end_id:     str | None      = None
    saw_header = False

    for raw_line in source.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("%%"):
            directives.append(raw_line)
            continue
        if _RE_HEADER.match(line):
            saw_header = True
            directives.append(raw_line)
            continue

        # Try edge first — edge lines contain `-->`, node decls don't.
        if "-->" in line:
            edge_m = _RE_EDGE.match(line)
            if not edge_m:
                raise MermaidParseError(f"unparseable edge line: {line!r}")

            src_tok = edge_m.group("src").strip()
            dst_tok = edge_m.group("dst").strip()
            label   = (edge_m.group("label") or "").strip() or None

            src_node = _ingest_endpoint(src_tok, nodes)
            dst_node = _ingest_endpoint(dst_tok, nodes)
            edges.append(Edge(source=src_node.id, target=dst_node.id, label=label))

            if src_node.type == "start":
                start_id = src_node.id
            if dst_node.type == "end":
                end_id = dst_node.id
            continue

        # Otherwise it's a standalone node declaration
        node = _parse_node_decl(line)
        if node is None:
            raise MermaidParseError(f"unrecognized line: {line!r}")
        _register_node(node, nodes)
        if node.type == "start":
            start_id = node.id
        if node.type == "end":
            end_id = node.id

    if not saw_header:
        raise MermaidParseError(
            "missing flowchart header — expected 'flowchart TD' or similar"
        )
    if start_id is None:
        raise MermaidParseError(
            "no start node — declare `START([label])` or use reserved id START"
        )
    if end_id is None:
        raise MermaidParseError(
            "no end node — declare `END([label])` or use reserved id END"
        )

    graph = Graph(
        nodes=nodes,
        edges=edges,
        start_id=start_id,
        end_id=end_id,
        directives=directives,
    )
    graph.validate()
    return graph


# ───────────────────────────────────────────────────────────────────────────
# Helpers
# ───────────────────────────────────────────────────────────────────────────

def _parse_node_decl(token: str) -> Node | None:
    """Parse a single node declaration token into a Node, or None if no match."""
    m = _RE_STADIUM.match(token)
    if m:
        nid = m.group(1)
        # Stadium inner text: either group 2 (double paren: A((x))) or group 3
        label = (m.group(2) if m.group(2) is not None else m.group(3)) or nid
        ntype = _stadium_type(nid, label)
        return Node(id=nid, label=label, type=ntype)

    m = _RE_DIAMOND.match(token)
    if m:
        nid, label = m.group(1), m.group(2) or m.group(1)
        return Node(id=nid, label=label, type="conditional")

    m = _RE_RECT.match(token)
    if m:
        nid, label = m.group(1), m.group(2) or m.group(1)
        return Node(id=nid, label=label, type="function")

    # Bare id — create a function node
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", token):
        if token in _RESERVED_START:
            return Node(id=token, label=token, type="start")
        if token in _RESERVED_END:
            return Node(id=token, label=token, type="end")
        return Node(id=token, label=token, type="function")

    return None


def _stadium_type(nid: str, label: str) -> str:
    """Stadium nodes default to start/end by reserved id or label keyword."""
    if nid in _RESERVED_START:
        return "start"
    if nid in _RESERVED_END:
        return "end"
    # Labels like "start" / "end" also work as a hint
    lbl = label.strip().lower()
    if lbl in {"start", "begin", "__start__"}:
        return "start"
    if lbl in {"end", "done", "__end__"}:
        return "end"
    # Fall back to function if the label isn't a start/end hint
    return "function"


def _ingest_endpoint(token: str, nodes: dict[str, Node]) -> Node:
    """Parse an edge endpoint (may be a shape decl or bare id) and register it."""
    node = _parse_node_decl(token)
    if node is None:
        raise MermaidParseError(f"unparseable edge endpoint: {token!r}")
    return _register_node(node, nodes)


def _register_node(node: Node, nodes: dict[str, Node]) -> Node:
    """Idempotent insert — prefer the more-informative declaration if we see
    the same id twice (e.g. shorthand use before a full declaration).
    """
    existing = nodes.get(node.id)
    if existing is None:
        nodes[node.id] = node
        return node
    # If existing is a bare/function but new has a more specific type, upgrade.
    if existing.type == "function" and node.type in ("start", "end", "conditional"):
        nodes[node.id] = node
        return node
    # Otherwise keep the existing — labels from the first declaration win.
    return existing
