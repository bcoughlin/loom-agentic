"""Tests for loom_agentic.policy.tool."""

from __future__ import annotations

import os

import pytest

from loom_agentic.policy import load_policy, report_position_tool

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def test_tool_schema_basic_shape():
    p = load_policy("sample", search_dirs=[FIXTURES])
    tool = report_position_tool(p)

    assert tool["name"] == "report_position"
    assert "kepler" not in tool["description"].lower()  # uses policy.name (sample)
    assert "sample" in tool["description"]

    schema = tool["input_schema"]
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {"node_id", "rationale"}


def test_node_id_enum_matches_policy_nodes():
    p = load_policy("sample", search_dirs=[FIXTURES])
    tool = report_position_tool(p)
    enum = tool["input_schema"]["properties"]["node_id"]["enum"]
    # Must include every node from the chart, in declaration order
    assert enum == list(p.node_ids)


def test_rationale_required_with_min_length():
    p = load_policy("sample", search_dirs=[FIXTURES])
    tool = report_position_tool(p)
    rat = tool["input_schema"]["properties"]["rationale"]
    assert rat["type"] == "string"
    assert rat["minLength"] == 1


def test_extra_properties_added():
    """Forward-compat hook used by plan 1 (working_memory_patch)."""
    p = load_policy("sample", search_dirs=[FIXTURES])
    tool = report_position_tool(p, extra_properties={
        "working_memory_patch": {"type": "object"},
    })
    assert "working_memory_patch" in tool["input_schema"]["properties"]
    # Not required by default
    assert "working_memory_patch" not in tool["input_schema"]["required"]


def test_extra_required_promotes_field():
    p = load_policy("sample", search_dirs=[FIXTURES])
    tool = report_position_tool(
        p,
        extra_properties={"hint": {"type": "string"}},
        extra_required=["hint"],
    )
    assert "hint" in tool["input_schema"]["required"]


def test_extra_required_for_unknown_field_raises():
    p = load_policy("sample", search_dirs=[FIXTURES])
    with pytest.raises(ValueError, match="not in properties"):
        report_position_tool(p, extra_required=["ghost"])


def test_extra_property_collision_raises():
    p = load_policy("sample", search_dirs=[FIXTURES])
    with pytest.raises(ValueError, match="collides"):
        report_position_tool(p, extra_properties={"node_id": {"type": "string"}})
