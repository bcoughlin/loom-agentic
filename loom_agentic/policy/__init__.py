"""Loom Policy — author Mermaid + YAML, get back a renderable Policy object.

Public API:
    from loom_agentic.policy import (
        load_policy, Policy, EdgePrompt,
        report_position_tool,
        policy_update_barrier_message,
    )

A `.policy.mmd` (Mermaid flowchart) + `.policy.yaml` (per-node/edge snippets +
globals + version) pair on disk becomes a `Policy` object that produces:
  - a 4-section prompt block via `Policy.render_prompt_section()`
  - a `report_position(node_id, rationale)` tool definition with the
    closed-vocabulary `node_id` enum baked in
  - a barrier message for resumed threads when the policy sha has changed

The loader reuses `loom_agentic.orchestrate.mermaid_parser` for syntax — one
parser, no drift.
"""

from .barrier import policy_update_barrier_message
from .loader import PolicyLoadError, load_policy
from .model import EdgePrompt, Policy
from .render import render_prompt_section
from .tool import report_position_tool

__all__ = [
    "EdgePrompt",
    "Policy",
    "PolicyLoadError",
    "load_policy",
    "policy_update_barrier_message",
    "render_prompt_section",
    "report_position_tool",
]
