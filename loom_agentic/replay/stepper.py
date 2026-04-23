"""Convert a raw event stream into a sequence of replay frames.

Each frame describes *what to highlight* at a given timestamp:
  - `active_node`  : which graph node is currently "active"
  - `active_edge`  : which edge is currently firing (if any)
  - `tool_name`    : if a tool is currently running, its name
  - `event`        : the raw LangGraph event that produced this frame
  - `summary`      : one-line human-readable description

The stepper filters noise aggressively — only events in the "story" tier
(per Loom's verbosity levels) produce frames by default. Raw events are
preserved for a "full log" view but don't drive the Mermaid highlight.

Frame transitions (for ReAct prebuilt agents):
  START
    -> `agent` active on on_chain_start(name="agent")
    -> `agent` done on on_chat_model_end
    -> if tool_calls present: `tools` active on on_tool_start
    -> `tools` done on on_tool_end (one per call)
    -> back to `agent` (loop iteration)
    -> END on on_chain_end(name="LangGraph")
"""

from __future__ import annotations

from dataclasses import dataclass, field


STORY_EVENTS = {"on_chat_model_end", "on_tool_start", "on_tool_end"}

# Nodes we highlight in the canonical ReAct graph. Names match what
# `create_react_agent` uses internally; `__start__` / `__end__` match the
# mermaid we synthesize in mermaid_for_run.
REACT_AGENT_NODE = "agent"
REACT_TOOLS_NODE = "tools"
REACT_END_NODE   = "__end__"


@dataclass
class Frame:
    """A single snapshot of the graph's visual state at one tick."""
    idx:          int
    ts:           str
    active_node:  str | None  = None
    active_edge:  tuple[str, str] | None = None  # (source, target)
    tool_name:    str | None  = None
    tool_args:    dict | None = None
    tool_output:  str | None  = None
    reply_text:   str | None  = None
    summary:      str         = ""
    event:        dict        = field(default_factory=dict)
    # True when this frame represents a Loom enforcement primitive
    # rejecting the tool call (e.g. reject_packed_dict). Distinct from
    # "tool errored" — a rejection is a policy course-correction, not a
    # crash, and the agent will retry on the next turn.
    rejected:     bool        = False


def frames_for_run(events: list[dict]) -> list[Frame]:
    """Fold a run's event stream into a list of visual frames."""
    frames: list[Frame] = []
    agent_was_active = False

    # Lead frame: the user's original message (if the structure event
    # carries one). Highlights __start__ -> agent so the replay reads
    # "user asked X -> agent thinks -> ...".
    # Emit a user-message frame and a thread-resume frame for EVERY
    # such event in time order — one thread now contains many turns'
    # worth of events, and each turn needs its own markers to read as
    # a coherent narrative.
    synthetic_markers: list[dict] = []
    for ev in events:
        etype = ev.get("event")
        if etype == "on_graph_structure" and ev.get("user_message"):
            synthetic_markers.append({
                "ts": ev.get("ts", ""),
                "active_node": "__start__",
                "active_edge": ("__start__", REACT_AGENT_NODE),
                "summary": f"\U0001f4ac {str(ev['user_message'])}",
                "event": ev,
            })
        elif etype == "on_thread_resume":
            count = ev.get("prior_message_count") or 0
            tools = ev.get("prior_tool_calls") or []
            seen: set[str] = set()
            uniq_tools: list[str] = []
            for t in tools:
                if t not in seen:
                    seen.add(t)
                    uniq_tools.append(t)
            tool_preview = f" \u00b7 prior tools: {', '.join(uniq_tools[:6])}" if uniq_tools else ""
            synthetic_markers.append({
                "ts": ev.get("ts", ""),
                "active_node": REACT_AGENT_NODE,
                "summary": f"\U0001f5c2 Resumed thread \u00b7 {count} prior message{'s' if count != 1 else ''}{tool_preview}",
                "event": ev,
            })
        elif etype == "on_policy_update":
            prior_v = ev.get("prior_policy_version") or "(unknown)"
            new_v   = ev.get("policy_version") or "(unknown)"
            prior_sha = (ev.get("prior_policy_sha") or "")[:8]
            new_sha   = (ev.get("policy_sha") or "")[:8]
            synthetic_markers.append({
                "ts": ev.get("ts", ""),
                "active_node": REACT_AGENT_NODE,
                "summary": (f"\U0001f4dc Policy update \u00b7 {prior_v} ({prior_sha}) "
                            f"\u2192 {new_v} ({new_sha}). Reminder injected."),
                "event": ev,
            })
    # Keep them in time order relative to each other; they'll be
    # reordered into the full timeline at render time when the loop
    # below appends the story-tier frames.
    for m in synthetic_markers:
        frames.append(Frame(
            idx=len(frames), ts=m["ts"],
            active_node=m.get("active_node"),
            active_edge=m.get("active_edge"),
            summary=m["summary"], event=m["event"],
        ))

    # Watch for a terminal event — either the clean on_chain_end or the
    # synthetic on_invocation_error emitted by tracing when the graph
    # raised. The latter carries error_class / error_message; surface
    # those in the closing frame so timed-out or failed runs are visible
    # and inspectable instead of silently trailing off.
    terminal_ts: str | None = None
    terminal_error: dict | None = None
    for ev in events:
        etype = ev.get("event")
        if etype == "on_chain_end" and ev.get("name") == "LangGraph":
            terminal_ts = ev.get("ts")
        elif etype == "on_invocation_error":
            terminal_ts = ev.get("ts")
            terminal_error = {
                "error_class":   ev.get("error_class", ""),
                "error_message": ev.get("error_message", ""),
            }

    for ev in events:
        etype = ev.get("event") or ""
        if etype not in STORY_EVENTS:
            continue

        idx = len(frames)
        ts  = ev.get("ts", "")

        if etype == "on_chat_model_end":
            tool_calls = ev.get("tool_calls") or []
            text = (ev.get("content") or "").strip()
            if tool_calls:
                names = [tc.get("name") for tc in tool_calls if tc.get("name")]
                first_tool = names[0] if names else REACT_TOOLS_NODE
                call_part = f"calling {', '.join(names) or '?'}"
                # Full text — UI handles single-line truncation when collapsed.
                summary = f"\U0001f9e0 {text}  \u27a4  {call_part}" if text else f"\U0001f9e0 {REACT_AGENT_NODE} {call_part}"
                frames.append(Frame(
                    idx=idx, ts=ts,
                    active_node=REACT_AGENT_NODE,
                    active_edge=(REACT_AGENT_NODE, _safe_id(first_tool)),
                    reply_text=text or None,
                    summary=summary, event=ev,
                ))
            else:
                frames.append(Frame(
                    idx=idx, ts=ts,
                    active_node=REACT_AGENT_NODE,
                    reply_text=text,
                    summary=f"\U0001f5e3\ufe0f {text}" if text else "\U0001f5e3\ufe0f (reply)",
                    event=ev,
                ))
            agent_was_active = True

        elif etype == "on_tool_start":
            tool = ev.get("tool") or ev.get("name") or "?"
            tool_args = ev.get("input") if isinstance(ev.get("input"), dict) else None
            # Full args json — UI truncates for display when collapsed.
            import json as _json
            args_str = _json.dumps(tool_args, default=str) if tool_args else ""
            frames.append(Frame(
                idx=idx, ts=ts,
                active_node=_safe_id(tool),
                # Keep the agent->tool edge lit while the tool is running, so
                # the replay visibly shows which branch the agent just took
                # in between on_chat_model_end (emitted the call) and
                # on_tool_end (tool returned). Without this, the node turns
                # green but the connecting arrow goes dark.
                active_edge=(REACT_AGENT_NODE, _safe_id(tool)),
                tool_name=tool,
                tool_args=tool_args,
                summary=f"\U0001f527 {tool}({args_str})",
                event=ev,
            ))

        elif etype == "on_tool_end":
            tool = ev.get("tool") or ev.get("name") or "?"
            output = ev.get("output") or ""
            lowered = output.lower() if isinstance(output, str) else ""

            # Three outcome classes for this frame:
            #   rejected — a Loom enforcement primitive (e.g.
            #      reject_packed_dict) returned an off-policy error
            #      that the model will see and retry from. NOT a
            #      crash; the agent got course-corrected.
            #   errored  — the tool errored or returned {ok:false}.
            #   success  — normal return.
            is_rejected = lowered.startswith("error:") and "off-policy" in lowered
            is_errored  = not is_rejected and (
                '"ok": false' in lowered
                or '"ok": null' in lowered
                or '"error":' in lowered
                or lowered.startswith("error:")
                or "timed out" in lowered
            )
            if is_rejected:
                ok_icon = "\u270b"
            elif is_errored:
                ok_icon = "\u274c"
            else:
                ok_icon = "\u2705"
            frames.append(Frame(
                idx=idx, ts=ts,
                active_node=_safe_id(tool),
                active_edge=(_safe_id(tool), REACT_AGENT_NODE),
                tool_name=tool,
                tool_output=output,
                summary=f"{ok_icon} {tool} \u2192 {output}",
                rejected=is_rejected,
                event=ev,
            ))

    # Frames came from two passes (synthetic markers first, then
    # story-tier events). Sort them into a single time-ordered stream
    # and reindex so the UI's cursor positions are monotonic.
    frames.sort(key=lambda f: f.ts or "")
    for i, f in enumerate(frames):
        f.idx = i

    # Append a terminal frame so the __end__ node + agent->__end__ edge
    # actually light up at the finish. On error, show the error class and
    # message instead of "run complete" so the failure is inspectable.
    if terminal_ts and frames:
        if terminal_error:
            err_cls = terminal_error.get("error_class") or "Error"
            err_msg = terminal_error.get("error_message") or ""
            preview = (err_msg[:120] + "\u2026") if len(err_msg) > 120 else err_msg
            summary = f"\u26a0\ufe0f {err_cls}" + (f": {preview}" if preview else "")
        else:
            summary = "\U0001f3c1 run complete"
        frames.append(Frame(
            idx=len(frames),
            ts=terminal_ts,
            active_node=REACT_END_NODE,
            active_edge=(REACT_AGENT_NODE, REACT_END_NODE),
            summary=summary,
            event={"event": "on_chain_end", "name": "LangGraph"},
        ))

    return frames


def _safe_id(name: str) -> str:
    """Match the sanitization rule used by mermaid_for_run._safe_id so the
    stepper's `active_node` matches the Mermaid node id verbatim.
    """
    import re
    if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", name):
        return name
    cleaned = re.sub(r"[^A-Za-z0-9_]", "_", name)
    if not cleaned or (not cleaned[0].isalpha() and cleaned[0] != "_"):
        cleaned = "t_" + cleaned
    return cleaned
