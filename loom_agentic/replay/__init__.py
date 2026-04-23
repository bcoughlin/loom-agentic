"""Loom Replay — temporal visual logs for LangGraph runs.

Public API:
    from loom_agentic.replay import load_events, group_by_run, frames_for_run, mermaid_for_run, Frame, Run

    events = load_events("path/to/events.jsonl")
    runs = group_by_run(events)
    for run in runs[:5]:
        frames = frames_for_run(run.events)
        mermaid = mermaid_for_run(run.events)
        # send frames + mermaid to your UI

Self-contained viewer:
    loom_agentic/replay/static/player.html

HTTP bridge (for admin dashboards):
    Expose GET /runs and GET /runs/{run_id}/frames from your backend;
    static/player.html expects JSON matching the Frame and Run shapes
    serialized by `serialize_run()`.
"""

from .loader  import Run, group_by_run, load_events
from .mermaid_for_run import CANONICAL_REACT_MERMAID, known_tools_by_agent, mermaid_for_run
from .stepper import Frame, frames_for_run


def serialize_run(run: Run, *, fallback_tools: list[str] | None = None) -> dict:
    """JSON-ready shape for the HTML player / HTTP clients.

    `fallback_tools` is passed through to `mermaid_for_run`, letting older
    runs that predate the on_graph_structure tracing event still render the
    full possible-path topology by reusing tool lists declared on newer
    runs of the same agent.
    """
    frames = frames_for_run(run.events)
    # Pull the most recent policy stamp from on_graph_structure events
    # — that's the version THIS run actually ran under, as distinct
    # from whatever the policy file says at read-time.
    run_policy_version: str | None = None
    run_policy_sha:     str | None = None
    # Pull the most recent context-carry snapshot so the admin can show
    # what the agent READ at prompt assembly (the verbatim system prompt
    # + optional section breakdown).
    context: dict | None = None
    for ev in reversed(run.events):
        if run_policy_version is None and ev.get("event") == "on_graph_structure":
            run_policy_version = ev.get("policy_version") or run_policy_version
            run_policy_sha     = ev.get("policy_sha")     or run_policy_sha
        if context is None and ev.get("event") == "on_context_carry":
            context = {
                "ts":                  ev.get("ts"),
                "system_prompt":       ev.get("system_prompt") or "",
                "system_prompt_bytes": ev.get("system_prompt_bytes")
                                       or len(ev.get("system_prompt") or ""),
                "prompt_sections":     ev.get("prompt_sections") or [],
                "first_user_message":  ev.get("first_user_message") or "",
                "policy_version":      ev.get("policy_version"),
                "policy_sha":          ev.get("policy_sha"),
            }
        if run_policy_version and run_policy_sha and context:
            break
    return {
        "run_id":       run.run_id,
        "agent":        run.agent,
        "thread_id":    run.thread_id,
        "started_at":   run.started_at,
        "ended_at":     run.ended_at,
        "duration_ms":  run.duration_ms,
        "event_count":  len(run.events),
        "mermaid":      mermaid_for_run(run.events, fallback_tools=fallback_tools),
        "frames":       [_frame_dict(f) for f in frames],
        "run_policy":   (
            {"version": run_policy_version, "sha": run_policy_sha}
            if run_policy_version else None
        ),
        "context":      context,
    }


def serialize_run_listing(run: Run) -> dict:
    """Compact summary for list views — no frames, no events."""
    tool_calls = sum(1 for e in run.events if e.get("event") == "on_tool_start")
    return {
        "run_id":      run.run_id,
        "agent":       run.agent,
        "thread_id":   run.thread_id,
        "started_at":  run.started_at,
        "ended_at":    run.ended_at,
        "duration_ms": run.duration_ms,
        "event_count": len(run.events),
        "tool_calls":  tool_calls,
    }


def _frame_dict(f: Frame) -> dict:
    return {
        "idx":         f.idx,
        "ts":          f.ts,
        "active_node": f.active_node,
        "active_edge": list(f.active_edge) if f.active_edge else None,
        "tool_name":   f.tool_name,
        "tool_args":   f.tool_args,
        "tool_output": f.tool_output,
        "reply_text":  f.reply_text,
        "summary":     f.summary,
        "kind":        f.event.get("event") if isinstance(f.event, dict) else None,
        "rejected":    f.rejected,
    }


__all__ = [
    "CANONICAL_REACT_MERMAID",
    "Frame",
    "Run",
    "frames_for_run",
    "group_by_run",
    "known_tools_by_agent",
    "load_events",
    "mermaid_for_run",
    "serialize_run",
    "serialize_run_listing",
]
