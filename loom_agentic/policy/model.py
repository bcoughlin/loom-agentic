"""Policy dataclass + the EdgePrompt struct it carries.

A `Policy` is the loaded, validated representation of a `.policy.mmd` +
`.policy.yaml` pair. It's frozen — mutations don't make sense at runtime;
re-load if the files change.

The `sha` is the first 8 chars of sha256 over the raw .mmd bytes. YAML-only
edits don't change the sha — that's a deliberate choice so the policy-update
barrier only fires on STRUCTURAL changes, not snippet wording tweaks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class EdgePrompt:
    """Per-edge guidance keyed by (source, target) node ids."""
    source: str
    target: str
    when:   str | None = None      # human-readable condition, optional
    prompt: str = ""               # the snippet shown in the assembled prompt


@dataclass(frozen=True)
class Policy:
    """Loaded + validated policy. Use `load_policy(...)` to construct."""

    name:          str                     # e.g. "kepler_director"
    version:       str                     # from yaml: "v1", "v2", ...
    sha:           str                     # first 8 of sha256(mermaid_bytes)
    mermaid:       str                     # raw .mmd contents (verbatim)
    globals:       tuple[str, ...]         # invariant snippets, ordered
    node_ids:      tuple[str, ...]         # all node ids, in declaration order
    node_prompts:  dict[str, str]          # node_id -> snippet (may omit nodes)
    edge_prompts:  tuple[EdgePrompt, ...]  # ordered, one per declared edge prompt
    raw_yaml:      dict[str, Any] = field(default_factory=dict)  # forward-compat

    def has_node(self, node_id: str) -> bool:
        return node_id in self.node_ids

    def render_prompt_section(self) -> str:
        """Assemble the 4-section prompt block. Delegates to render module
        to keep the dataclass thin and the renderer testable in isolation.
        """
        # Local import avoids circular import at module load
        from .render import render_prompt_section as _render
        return _render(self)
