"""Loom enforcement primitives — the hard layer.

Loom's thesis is that authored policy should have multiple enforcement
layers, so no single layer is load-bearing alone:

  1. Prompt-level (rendered flowchart + invariants + per-node snippets)
  2. Position-reporting contract (report_position tool)
  3. Rationale requirement (audited in the admin bubble)
  4. **Tool-level rejection** — this module

Layers 1-3 make a bug diagnosable; layer 4 is the counterweight when
prompt rules demonstrably lose under pressure. Every primitive here
returns a string the caller can return verbatim to the model as the
tool result, forcing a retry — OR None when the call is acceptable.

These primitives are domain-agnostic mechanisms. Which primitives are
applied to which tools is the consuming app's decision, configured
alongside the tool definitions themselves.

Call pattern inside a LangChain @tool wrapper:

    from loom_agentic.enforcement import reject_packed_dict
    err = reject_packed_dict('apply_correction', value)
    if err: return err
    return _call('apply_correction', {...})

Current primitives:
  - `reject_packed_dict(tool_name, value)` — reject dict values with
    more than one key. For tools that represent one atomic fact per
    call; disable in consumers where dict-valued atoms are legitimate.

Expected additions (ongoing):
  - `reject_unknown_node_id(allowed, node_id)` — factor this out of
    report_position so other vocabulary-gated tools can reuse it.
  - `reject_missing_rationale(value)` — likewise.
  - `reject_stale_version(expected_sha, got_sha)` — enforce policy
    sha stamps on tool calls that must pin to a version.
"""

from __future__ import annotations

from typing import Any


def reject_packed_dict(tool_name: str, value: Any) -> str | None:
    """Return an error string if `value` is a dict with more than one
    key — callers return this to the model verbatim as the tool result,
    forcing a retry with split calls. Returns None when the value is
    acceptable (scalar, None, list, or a 1-key dict).

    Rationale: agents frequently pack multiple atomic facts into one
    write-tool call as a single dict, which LOOKS like obeying a
    "write progressively" prompt rule but isn't. Structural rejection
    is the only reliable counterweight.
    """
    if isinstance(value, dict) and len(value) > 1:
        keys = ', '.join(f'"{k}"' for k in list(value.keys())[:6])
        return (f"ERROR: {tool_name} received a dict value with "
                f"{len(value)} keys ({keys}). This is off-policy — each "
                f"write must represent one atomic fact. Split into "
                f"{len(value)} parallel tool calls this turn, one per "
                f"key. Do NOT repack into a dict.")
    return None
