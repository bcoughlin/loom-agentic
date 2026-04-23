"""Smoke test: load a synthetic run, compute frames, validate shape.

Run: PYTHONPATH=. python3 loom_agentic/replay/tests/test_replay_smoke.py
"""

from __future__ import annotations

from loom_agentic.replay import (
    frames_for_run,
    group_by_run,
    mermaid_for_run,
    serialize_run,
)

SYNTHETIC_EVENTS = [
    {"event": "on_chain_start", "name": "LangGraph",   "run_id": "r1", "ts": "2026-04-17T10:00:00.000Z", "agent": "my_agent"},
    {"event": "on_chain_start", "name": "agent",       "run_id": "r1", "ts": "2026-04-17T10:00:00.100Z"},
    {"event": "on_chat_model_end", "name": "ChatAnthropic", "run_id": "r1", "ts": "2026-04-17T10:00:01.000Z",
     "tool_calls": [{"name": "view_screenshot", "args": {"instructions": "focus on building levels"}}],
     "content": "I'll look at the screenshot first."},
    {"event": "on_tool_start", "name": "view_screenshot", "tool": "view_screenshot", "run_id": "r1",
     "ts": "2026-04-17T10:00:01.200Z", "input": {"instructions": "focus on building levels"}},
    {"event": "on_tool_end", "name": "view_screenshot", "tool": "view_screenshot", "run_id": "r1",
     "ts": "2026-04-17T10:00:02.000Z", "output": "Screenshot shows HQ at level 14 and a hero selection menu."},
    {"event": "on_chat_model_end", "name": "ChatAnthropic", "run_id": "r1", "ts": "2026-04-17T10:00:03.000Z",
     "tool_calls": [], "content": "HQ is at level 14. Anything else you'd like me to check?"},
    {"event": "on_chain_end", "name": "LangGraph", "run_id": "r1", "ts": "2026-04-17T10:00:03.500Z"},
]


def main() -> None:
    runs = group_by_run(SYNTHETIC_EVENTS)
    assert len(runs) == 1
    run = runs[0]
    assert run.run_id == "r1"
    assert run.agent  == "my_agent"
    assert run.duration_ms > 0

    frames = frames_for_run(run.events)
    # 4 story-tier events: chat_end (tool), tool_start, tool_end, chat_end (reply)
    assert len(frames) == 4, f"expected 4 frames, got {len(frames)}: {[f.summary for f in frames]}"

    # Frame 0: agent called view_screenshot
    assert frames[0].active_node == "agent"
    assert frames[0].active_edge == ("agent", "tools")
    assert "view_screenshot" in frames[0].summary

    # Frame 1: tool_start
    assert frames[1].active_node == "tools"
    assert frames[1].tool_name   == "view_screenshot"

    # Frame 2: tool_end loops back to agent
    assert frames[2].active_edge == ("tools", "agent")
    assert "HQ at level 14" in frames[2].tool_output

    # Frame 3: final reply
    assert frames[3].active_node == "agent"
    assert frames[3].reply_text and "HQ is at level 14" in frames[3].reply_text

    # Mermaid resolution
    mermaid = mermaid_for_run(run.events)
    assert "flowchart" in mermaid
    assert "agent" in mermaid

    # Serialization is JSON-clean
    import json
    payload = serialize_run(run)
    json.dumps(payload)  # would raise if anything isn't serializable
    assert payload["run_id"] == "r1"
    assert len(payload["frames"]) == 4

    print("Replay smoke test OK")
    print(f"   {len(frames)} frames produced from {len(run.events)} raw events")
    for f in frames:
        print(f"   #{f.idx}: {f.summary}")


if __name__ == "__main__":
    main()
