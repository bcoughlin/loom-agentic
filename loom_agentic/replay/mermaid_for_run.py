"""Pick / synthesize the Mermaid source for a run.

Default strategy: if the run's events carry an explicit graph structure (an
`on_graph_structure` event with a `mermaid` field), use that. Otherwise
synthesize a per-run mermaid that expands LangGraph's `tools` meta-node into
one node per tool that actually fired — so the player can light up the
specific tool during replay instead of the abstract bucket.

Example synthesized mermaid when a run fired `view_screenshot` and
`write_mechanic`:

    flowchart TD
        __start__([start])
        agent[agent]
        view_screenshot[view_screenshot]
        write_mechanic[write_mechanic]
        __end__([end])
        __start__ --> agent
        agent --> view_screenshot
        view_screenshot --> agent
        agent --> write_mechanic
        write_mechanic --> agent
        agent -->|done| __end__

Nodes ids are the tool names verbatim. If a tool name isn't a valid Mermaid
id (contains dots, hyphens, etc.), we sanitize to `tool_<idx>` and keep the
label.
"""

from __future__ import annotations

import re


CANONICAL_REACT_MERMAID = """flowchart LR
    __start__([start])
    agent[agent]
    tools[tools]
    __end__([end])
    __start__ --> agent
    agent -->|tool_calls| tools
    agent -->|done| __end__
    tools --> agent
""".strip()


_VALID_MERMAID_ID = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def mermaid_for_run(
    events: list[dict],
    *,
    fallback_tools: list[str] | None = None,
) -> str:
    """Return Mermaid source to render for this run.

    Resolution order:
      1. `on_graph_structure` event on *this* run with a `mermaid` field
      2. `on_graph_structure` event on *this* run with a `tools` list
      3. `fallback_tools` — caller-supplied list (typically derived from
         *other* runs of the same agent that do have a structure event, so
         older pre-instrumentation runs can still show the full topology)
      4. Tools the run actually fired
      5. Canonical abstract ReAct graph
    """
    for ev in events:
        if ev.get("event") == "on_graph_structure":
            mermaid = ev.get("mermaid") or ev.get("data", {}).get("mermaid")
            if mermaid:
                return mermaid

    for ev in events:
        if ev.get("event") == "on_graph_structure" and ev.get("tools"):
            return _synthesize_react_with_tools(list(ev["tools"]))

    if fallback_tools:
        return _synthesize_react_with_tools(list(fallback_tools))

    tools_fired = _extract_unique_tools(events)
    if tools_fired:
        return _synthesize_react_with_tools(tools_fired)

    return CANONICAL_REACT_MERMAID


def known_tools_by_agent(all_events: list[dict]) -> dict[str, list[str]]:
    """Scan a corpus of events for the most recent `on_graph_structure` per
    agent. Useful for the backend: one call gives it a dict it can pass as
    `fallback_tools` when serializing older runs that predate the tracing
    change.
    """
    # Sort by ts so we pick the newest declaration per agent
    events = sorted(all_events, key=lambda e: e.get("ts", ""))
    latest: dict[str, list[str]] = {}
    for ev in events:
        if ev.get("event") != "on_graph_structure":
            continue
        agent = ev.get("agent") or ""
        tools = ev.get("tools") or []
        if agent and tools:
            latest[agent] = list(tools)
    return latest


def _extract_unique_tools(events: list[dict]) -> list[str]:
    """Pull the distinct tool names that actually ran, preserving first-seen order."""
    seen: dict[str, None] = {}  # ordered set
    for ev in events:
        if ev.get("event") != "on_tool_start":
            continue
        name = ev.get("tool") or ev.get("name") or ""
        if name and name not in seen:
            seen[name] = None
    return list(seen.keys())


def _synthesize_react_with_tools(tools: list[str]) -> str:
    """Build a Mermaid flowchart: agent <-> each-tool, plus start/end.

    Uses LR layout so the tool nodes stack vertically rather than fanning
    horizontally — fits better in a side panel and scrolls vertically
    instead of requiring a wide horizontal scroll.
    """
    lines = ["flowchart LR",
             "    __start__([start])",
             "    agent[agent]"]

    # Each tool gets its own node. Keep a mapping in case we had to sanitize.
    for raw in tools:
        node_id = _safe_id(raw)
        lines.append(f"    {node_id}[{raw}]")

    lines.append("    __end__([end])")
    lines.append("    __start__ --> agent")
    for raw in tools:
        node_id = _safe_id(raw)
        lines.append(f"    agent --> {node_id}")
        lines.append(f"    {node_id} --> agent")
    lines.append("    agent -->|done| __end__")

    return "\n".join(lines)


def _safe_id(name: str) -> str:
    """Mermaid ids must match [A-Za-z_][A-Za-z0-9_]* — sanitize anything else."""
    if _VALID_MERMAID_ID.match(name):
        return name
    # Replace offending chars with underscores, prefix with `t_` if needed
    cleaned = re.sub(r"[^A-Za-z0-9_]", "_", name)
    if not cleaned or not cleaned[0].isalpha() and cleaned[0] != "_":
        cleaned = "t_" + cleaned
    return cleaned
