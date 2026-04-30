"""Tests for loom_agentic.policy.loader."""

from __future__ import annotations

import os

import pytest

from loom_agentic.policy import PolicyLoadError, load_policy

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def test_loads_sample_policy():
    p = load_policy("sample", search_dirs=[FIXTURES])
    assert p.name == "sample"
    assert p.version == "v1"
    # sha is the first 8 chars of sha256 over the .mmd bytes — deterministic
    # for a given fixture content. Just check shape, not value (so editing
    # the fixture doesn't force a test edit).
    assert len(p.sha) == 8
    assert all(c in "0123456789abcdef" for c in p.sha)


def test_node_ids_in_declaration_order():
    p = load_policy("sample", search_dirs=[FIXTURES])
    # First few should match the order they appear in the .mmd
    assert p.node_ids[:4] == ("START", "orient", "route", "resolve_thread")
    # All authored nodes are present
    for nid in (
        "orient", "route", "resolve_thread", "pick_target", "detecting",
        "identifying", "classify_match", "answer", "proposing_bind",
        "awaiting_user_answer", "proposing",
    ):
        assert p.has_node(nid), f"missing node: {nid}"


def test_globals_loaded():
    p = load_policy("sample", search_dirs=[FIXTURES])
    assert len(p.globals) == 2
    assert "Never invent coordinates" in p.globals[0]


def test_node_prompts_loaded():
    p = load_policy("sample", search_dirs=[FIXTURES])
    assert "resolve_thread" in p.node_prompts
    assert "user's reply IS the answer" in p.node_prompts["resolve_thread"]
    # Nodes without prompts in YAML are simply absent — not empty strings
    assert "pick_target" not in p.node_prompts


def test_edge_prompts_loaded():
    p = load_policy("sample", search_dirs=[FIXTURES])
    edges = p.edge_prompts
    assert len(edges) == 2
    e1 = next(e for e in edges if e.source == "route" and e.target == "resolve_thread")
    assert e1.when == "has_open_question is true"
    assert "Acknowledge the user's reply" in e1.prompt


def test_missing_files_raises(tmp_path):
    with pytest.raises(PolicyLoadError, match="not found"):
        load_policy("nonexistent", search_dirs=[str(tmp_path)])


def test_partial_files_raises(tmp_path):
    # Only the .mmd, missing the .yaml — clearer error than "not found"
    (tmp_path / "x.policy.mmd").write_text("flowchart TD\n  START([s]) --> END([e])\n")
    with pytest.raises(PolicyLoadError, match="missing"):
        load_policy("x", search_dirs=[str(tmp_path)])


def test_yaml_references_unknown_node_raises(tmp_path):
    (tmp_path / "x.policy.mmd").write_text(
        "flowchart TD\n  START([s]) --> a\n  a[A] --> END([e])\n"
    )
    (tmp_path / "x.policy.yaml").write_text(
        'version: "v1"\nnodes:\n  ghost:\n    prompt: "no"\n'
    )
    with pytest.raises(PolicyLoadError, match="not in"):
        load_policy("x", search_dirs=[str(tmp_path)])


def test_yaml_missing_version_raises(tmp_path):
    (tmp_path / "x.policy.mmd").write_text(
        "flowchart TD\n  START([s]) --> END([e])\n"
    )
    (tmp_path / "x.policy.yaml").write_text("globals: []\n")
    with pytest.raises(PolicyLoadError, match="version"):
        load_policy("x", search_dirs=[str(tmp_path)])


def test_search_dirs_first_match_wins(tmp_path):
    d1 = tmp_path / "first"; d1.mkdir()
    d2 = tmp_path / "second"; d2.mkdir()
    # Only d2 has the files — loader should walk past d1
    (d2 / "x.policy.mmd").write_text(
        "flowchart TD\n  START([s]) --> a\n  a[A] --> END([e])\n"
    )
    (d2 / "x.policy.yaml").write_text('version: "v9"\n')
    p = load_policy("x", search_dirs=[str(d1), str(d2)])
    assert p.version == "v9"


def test_yaml_only_partial_in_dir_raises(tmp_path):
    # Same dir has only the yaml — partial-match error fires
    (tmp_path / "x.policy.yaml").write_text('version: "v1"\n')
    with pytest.raises(PolicyLoadError, match="missing"):
        load_policy("x", search_dirs=[str(tmp_path)])
