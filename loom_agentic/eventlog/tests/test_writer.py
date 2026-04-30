"""Tests for loom_agentic.eventlog.writer.

Round-trip is the critical assertion: events the writer emits must parse
cleanly through replay.loader and produce sensible Frames via the stepper.
"""

from __future__ import annotations

import json
import os

import pytest

from loom_agentic.eventlog import EventWriter, emit_event
from loom_agentic.replay import frames_for_run, group_by_run, load_events


def _read_jsonl(path: str) -> list[dict]:
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def test_writer_creates_parent_dir(tmp_path):
    nested = tmp_path / "a" / "b" / "events.jsonl"
    EventWriter(path=str(nested), agent="x")
    assert nested.parent.is_dir()


def test_writer_emits_chain_start_by_default(tmp_path):
    p = tmp_path / "events.jsonl"
    EventWriter(path=str(p), agent="x")
    rows = _read_jsonl(str(p))
    assert len(rows) == 1
    assert rows[0]["event"] == "on_chain_start"


def test_writer_can_skip_chain_start(tmp_path):
    p = tmp_path / "events.jsonl"
    EventWriter(path=str(p), agent="x", emit_run_start=False)
    assert not p.exists() or _read_jsonl(str(p)) == []


def test_typed_helpers_round_trip_through_loader(tmp_path):
    p = tmp_path / "events.jsonl"
    w = EventWriter(
        path=str(p), agent="kepler_director",
        policy_version="v1", policy_sha="abc12345",
    )
    w.emit_graph_structure(
        mermaid="flowchart TD\n  START([s]) --> a\n  a[A] --> END([e])\n",
        tools=["dino_detect"],
        user_message="identify this character",
    )
    w.emit_position_report(node_id="orient", rationale="reading user intent")
    w.emit_chat_model_end(
        content="Let me detect the face",
        tool_calls=[{"name": "dino_detect", "input": {"prompt": "face"}}],
    )
    w.emit_position_report(node_id="detecting", rationale="dino face crop")
    w.emit_tool_start(tool="dino_detect", input={"prompt": "face"})
    w.emit_tool_end(tool="dino_detect", output={"hits": 3, "top_score": 0.78})
    w.emit_chain_end()

    events = load_events(str(p))
    runs = group_by_run(events)
    assert len(runs) == 1
    run = runs[0]
    assert run.agent == "kepler_director"
    assert len(run.events) >= 7


def test_position_report_drives_active_node_in_stepper(tmp_path):
    p = tmp_path / "events.jsonl"
    w = EventWriter(path=str(p), agent="x")
    w.emit_graph_structure(
        mermaid="flowchart TD\n  START([s]) --> orient\n  orient[O] --> END([e])\n",
    )
    w.emit_position_report(node_id="orient", rationale="testing")
    w.emit_chain_end()

    events = load_events(str(p))
    frames = frames_for_run(events)
    pos_frames = [f for f in frames if f.reported_node_id == "orient"]
    assert len(pos_frames) == 1
    assert pos_frames[0].active_node == "orient"
    assert pos_frames[0].reported_rationale == "testing"


def test_tool_frame_inherits_recent_position_report(tmp_path):
    p = tmp_path / "events.jsonl"
    w = EventWriter(path=str(p), agent="x")
    w.emit_graph_structure(
        mermaid=(
            "flowchart TD\n  START([s]) --> detecting\n"
            "  detecting[D] --> END([e])\n"
        ),
    )
    w.emit_position_report(node_id="detecting", rationale="dino time")
    w.emit_tool_start(tool="dino_detect", input={"prompt": "face"})
    w.emit_tool_end(tool="dino_detect", output="ok")

    events = load_events(str(p))
    frames = frames_for_run(events)
    tool_frames = [f for f in frames if f.tool_name == "dino_detect"]
    assert len(tool_frames) == 2  # start + end
    for f in tool_frames:
        assert f.reported_node_id == "detecting"
        assert f.reported_rationale == "dino time"
    # Active edge for tool_start should anchor at the reported node, not "agent"
    start = tool_frames[0]
    assert start.active_edge[0] == "detecting"


def test_tool_frame_without_position_falls_back_to_agent(tmp_path):
    """Existing LangGraph runs without on_position_report still render."""
    p = tmp_path / "events.jsonl"
    w = EventWriter(path=str(p), agent="x")
    w.emit_tool_start(tool="dino_detect", input={"prompt": "face"})
    w.emit_tool_end(tool="dino_detect", output="ok")

    events = load_events(str(p))
    frames = frames_for_run(events)
    tool_start = next(f for f in frames if f.tool_name == "dino_detect" and not f.tool_output)
    assert tool_start.active_edge[0] == "agent"
    assert tool_start.reported_node_id is None


def test_thread_id_defaults_to_run_id(tmp_path):
    p = tmp_path / "events.jsonl"
    w = EventWriter(path=str(p), agent="x")
    rows = _read_jsonl(str(p))
    assert rows[0]["thread_id"] == w.run_id


def test_emit_event_one_off(tmp_path):
    p = tmp_path / "events.jsonl"
    rec = emit_event(str(p), "on_chain_end", {"name": "LangGraph"}, agent="x")
    assert rec["event"] == "on_chain_end"
    rows = _read_jsonl(str(p))
    assert rows[0]["event"] == "on_chain_end"


def test_writer_stamps_policy_version_on_every_event(tmp_path):
    p = tmp_path / "events.jsonl"
    w = EventWriter(
        path=str(p), agent="x",
        policy_version="v3", policy_sha="deadbeef",
    )
    w.emit_position_report(node_id="orient", rationale="x")
    rows = _read_jsonl(str(p))
    for r in rows:
        assert r["policy_version"] == "v3"
        assert r["policy_sha"] == "deadbeef"
