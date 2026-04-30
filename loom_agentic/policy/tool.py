"""report_position tool definition generator.

Provider-agnostic — emits a JSON Schema dict that Anthropic's `tools` array,
Google's `function_declarations`, and OpenAI's `tools` all accept (with each
provider's wrapping). Caller adapts the wrapping; the schema body is the same.

The closed-vocabulary `node_id` enum is the structural payoff: Anthropic's API
rejects tool calls with non-enum values BEFORE they reach your handler. That's
free layer-4 enforcement on node-id hallucination — no prompt rule needed.
"""

from __future__ import annotations

from typing import Any

from .model import Policy


def report_position_tool(
    policy: Policy,
    *,
    extra_properties: dict[str, Any] | None = None,
    extra_required: list[str] | None = None,
) -> dict:
    """Build the report_position tool definition for a given policy.

    Args:
      policy: the active Policy — its `node_ids` populate the closed enum.
      extra_properties: optional additional JSON Schema properties to add to
                        the tool input. Used by plan 1 (working_memory_patch)
                        without restructuring this generator.
      extra_required: optional additional required-field names. Caller is
                      responsible for ensuring they appear in extra_properties.

    Returns a dict in the shape:
      {
          "name": "report_position",
          "description": "...",
          "input_schema": {
              "type": "object",
              "properties": {...},
              "required": [...],
          },
      }
    """
    properties: dict[str, Any] = {
        "node_id": {
            "type": "string",
            "enum": list(policy.node_ids),
            "description": (
                "Your current position on the policy flowchart. "
                "Must be one of the listed node ids."
            ),
        },
        "rationale": {
            "type": "string",
            "description": (
                "One sentence: why are you at this node right now? "
                "Used for replay debugging — be specific."
            ),
            "minLength": 1,
        },
    }
    required: list[str] = ["node_id", "rationale"]

    if extra_properties:
        for k, v in extra_properties.items():
            if k in properties:
                raise ValueError(
                    f"extra_properties key {k!r} collides with a built-in field"
                )
            properties[k] = v
    if extra_required:
        for k in extra_required:
            if k not in properties:
                raise ValueError(
                    f"extra_required entry {k!r} not in properties — "
                    f"add it via extra_properties first"
                )
            if k not in required:
                required.append(k)

    return {
        "name": "report_position",
        "description": (
            f"Report your current position on the {policy.name} policy "
            f"flowchart. REQUIRED as a parallel tool call whenever you "
            f"invoke any other tool. Pure observability — does not change "
            f"any state on its own."
        ),
        "input_schema": {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        },
    }
