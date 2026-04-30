"""Tests for loom_agentic.policy.render."""

from __future__ import annotations

import os

from loom_agentic.policy import load_policy

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def test_render_includes_all_four_sections():
    p = load_policy("sample", search_dirs=[FIXTURES])
    out = p.render_prompt_section()

    assert "## Loom policy: sample (v1, sha " in out
    assert "### Invariants" in out
    assert "### Flowchart" in out
    assert "```mermaid" in out
    assert "### Per-node and per-edge guidance" in out
    assert "### Position-reporting contract" in out


def test_render_node_prompts_in_chart_order():
    p = load_policy("sample", search_dirs=[FIXTURES])
    out = p.render_prompt_section()

    # `orient` is declared before `resolve_thread` in the .mmd, so it
    # should render first in the per-node section
    orient_pos = out.index("**Node `orient`**")
    resolve_pos = out.index("**Node `resolve_thread`**")
    answer_pos = out.index("**Node `answer`**")
    assert orient_pos < resolve_pos < answer_pos


def test_render_edge_when_clause():
    p = load_policy("sample", search_dirs=[FIXTURES])
    out = p.render_prompt_section()
    # Edge with a `when:` should render the condition inline
    assert "**Edge `route → resolve_thread`** (when has_open_question is true)" in out
    assert "**Edge `classify_match → answer`** (when score >= 0.85)" in out


def test_render_position_contract_lists_all_nodes():
    p = load_policy("sample", search_dirs=[FIXTURES])
    out = p.render_prompt_section()
    # Contract should enumerate every node id, including ones without prompts
    for nid in (
        "orient", "resolve_thread", "pick_target", "detecting", "identifying",
        "classify_match", "answer", "proposing", "proposing_bind",
        "awaiting_user_answer",
    ):
        assert f"`{nid}`" in out, f"missing node in contract: {nid}"


def test_render_invariants_section_omitted_when_no_globals(tmp_path):
    (tmp_path / "x.policy.mmd").write_text(
        "flowchart TD\n  START([s]) --> a\n  a[A] --> END([e])\n"
    )
    (tmp_path / "x.policy.yaml").write_text('version: "v1"\n')
    p = load_policy("x", search_dirs=[str(tmp_path)])
    out = p.render_prompt_section()
    assert "### Invariants" not in out
    # But contract still renders
    assert "### Position-reporting contract" in out


def test_render_per_node_section_omitted_when_no_prompts(tmp_path):
    (tmp_path / "x.policy.mmd").write_text(
        "flowchart TD\n  START([s]) --> a\n  a[A] --> END([e])\n"
    )
    (tmp_path / "x.policy.yaml").write_text('version: "v1"\n')
    p = load_policy("x", search_dirs=[str(tmp_path)])
    out = p.render_prompt_section()
    assert "### Per-node and per-edge guidance" not in out
