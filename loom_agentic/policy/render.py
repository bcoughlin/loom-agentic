"""Render a Policy into the 4-section prompt block.

Output shape (matches DOCS.md):
  ## Loom policy: <name> (<version>, sha <sha>)

  ### Invariants (apply at every node)
  - <global 1>
  - <global 2>

  ### Flowchart
  ```mermaid
  <verbatim .mmd>
  ```

  ### Per-node and per-edge guidance
  **Node `<id>`** — <snippet>
  **Edge `<src> → <dst>`** (when <condition>) — <snippet>

  ### Position-reporting contract
  Whenever you call any tool, you MUST also call `report_position(node_id, rationale)`
  as a parallel tool call.
  - Allowed `node_id` values: `<a>`, `<b>`, `<c>`
  - `rationale`: one sentence — why are you at this node right now?
"""

from __future__ import annotations

from .model import Policy


def render_prompt_section(policy: Policy) -> str:
    parts: list[str] = []

    parts.append(f"## Loom policy: {policy.name} ({policy.version}, sha {policy.sha})")

    if policy.globals:
        parts.append("")
        parts.append("### Invariants (apply at every node)")
        for g in policy.globals:
            parts.append(f"- {g}")

    parts.append("")
    parts.append("### Flowchart")
    parts.append("```mermaid")
    parts.append(policy.mermaid.rstrip())
    parts.append("```")

    has_node_prompts = bool(policy.node_prompts)
    has_edge_prompts = bool(policy.edge_prompts)
    if has_node_prompts or has_edge_prompts:
        parts.append("")
        parts.append("### Per-node and per-edge guidance")
        # Nodes first, in declaration order from the .mmd (filtered to those
        # with prompts) so the section reads top-to-bottom of the chart.
        for nid in policy.node_ids:
            snippet = policy.node_prompts.get(nid)
            if snippet:
                parts.append(f"**Node `{nid}`** — {snippet}")
        # Then edges, in YAML declaration order.
        for ep in policy.edge_prompts:
            if not ep.prompt:
                continue
            arrow_label = ""
            if ep.when:
                arrow_label = f" (when {ep.when})"
            parts.append(
                f"**Edge `{ep.source} → {ep.target}`**{arrow_label} — {ep.prompt}"
            )

    parts.append("")
    parts.append("### Position-reporting contract")
    parts.append(
        "Whenever you call any tool, you MUST also call "
        "`report_position(node_id, rationale)` as a parallel tool call."
    )
    allowed = ", ".join(f"`{n}`" for n in policy.node_ids)
    parts.append(f"- Allowed `node_id` values: {allowed}")
    parts.append("- `rationale`: one sentence — why are you at this node right now?")

    return "\n".join(parts) + "\n"
