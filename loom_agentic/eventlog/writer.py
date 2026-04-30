"""JSONL event writer producing records `replay/loader.py` can read.

Format conventions (derived from reading loader.py + stepper.py + mermaid_for_run.py):

  Every record is a JSON object on its own line with at minimum:
    ts                ISO-8601 timestamp string (sortable lexicographically)
    event             event type (e.g. "on_tool_start", "on_position_report")
    run_id            unique per writer instance
    invocation_id     same as run_id for our case (no nested LangGraph runnables)
    trace_id          same as run_id
    agent             agent name (string), used for grouping in admin views
    thread_id         optional — caller can pass to enable cross-session grouping
    policy_version    optional — policy active for this event
    policy_sha        optional

  Per-event-type extra fields:
    on_graph_structure  mermaid: str, tools: list[str], user_message: str?
    on_chain_start      name: str (typically "LangGraph" — we mimic it for kepler-style runs)
    on_chain_end        name: str
    on_chat_model_end   content: str, tool_calls: list[{name, input, ...}]
    on_tool_start       tool: str, input: dict
    on_tool_end         tool: str, output: str (or json-stringified)
    on_position_report  node_id: str, rationale: str
    on_thread_resume    prior_message_count: int, prior_tool_calls: list[str]
    on_policy_update    prior_policy_version: str, prior_policy_sha: str,
                        policy_version: str, policy_sha: str
    on_invocation_error error_class: str, error_message: str
    on_context_carry    system_prompt: str, system_prompt_bytes: int,
                        prompt_sections: list[dict], first_user_message: str

The writer takes a thread lock so concurrent emit() calls from different
async coroutines or tasks don't interleave partial lines.
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any


def _now_iso() -> str:
    """Return a UTC ISO-8601 string with a trailing Z. Sortable lexicographically."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class EventWriter:
    """Append-only JSONL writer.

    One writer per session/run. The run_id is generated at construction
    unless supplied; same value used for invocation_id and trace_id since
    kepler-style runs don't have nested LangGraph runnables.
    """

    def __init__(
        self,
        path: str,
        *,
        agent: str,
        policy_version: str | None = None,
        policy_sha: str | None = None,
        run_id: str | None = None,
        thread_id: str | None = None,
        emit_run_start: bool = True,
    ):
        self.path = path
        self.agent = agent
        self.policy_version = policy_version
        self.policy_sha = policy_sha
        self.run_id = run_id or uuid.uuid4().hex[:12]
        self.thread_id = thread_id or self.run_id  # default: thread == run
        self._lock = threading.Lock()

        # Make sure the parent dir exists; failing here gives a clearer
        # error than a deferred ENOENT during the first emit.
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)

        if emit_run_start:
            # Mimic LangGraph's chain_start so loader's fallback grouping
            # path also segments correctly. Stepper currently doesn't
            # generate a frame for this — it's pure boundary signal.
            self.emit("on_chain_start", {"name": "LangGraph"})

    # ────────────────────────────────────────────────────────────────────
    # Generic emit
    # ────────────────────────────────────────────────────────────────────

    def emit(self, event_type: str, payload: dict[str, Any] | None = None) -> dict:
        """Write one event. Returns the record (for tests / callers that want it)."""
        record: dict[str, Any] = {
            "ts":            _now_iso(),
            "event":         event_type,
            "run_id":        self.run_id,
            "invocation_id": self.run_id,
            "trace_id":      self.run_id,
            "agent":         self.agent,
        }
        if self.thread_id:
            record["thread_id"] = self.thread_id
        if self.policy_version is not None:
            record["policy_version"] = self.policy_version
        if self.policy_sha is not None:
            record["policy_sha"] = self.policy_sha
        if payload:
            # Payload keys override base record keys EXCEPT the identity
            # ones (run_id/invocation_id/trace_id/agent/event) — those are
            # writer-controlled. ts can be overridden for synthetic events.
            for k, v in payload.items():
                if k in {"run_id", "invocation_id", "trace_id", "agent", "event"}:
                    continue
                record[k] = v

        line = json.dumps(record, default=str)
        with self._lock:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        return record

    # ────────────────────────────────────────────────────────────────────
    # Typed helpers — match the event vocabulary stepper consumes
    # ────────────────────────────────────────────────────────────────────

    def emit_graph_structure(
        self,
        *,
        mermaid: str,
        tools: list[str] | None = None,
        user_message: str | None = None,
    ) -> dict:
        """Declare the chart this run runs against. Drives `mermaid_for_run`.

        `user_message` (when supplied) becomes the lead frame in stepper.
        """
        payload: dict[str, Any] = {"mermaid": mermaid}
        if tools is not None:
            payload["tools"] = list(tools)
        if user_message is not None:
            payload["user_message"] = user_message
        return self.emit("on_graph_structure", payload)

    def emit_user_message(self, text: str) -> dict:
        """Convenience: emit an on_graph_structure with just the user_message
        field set. Useful for follow-up turns on the same thread that don't
        re-declare the chart but DO want the user-bubble in the timeline.
        """
        return self.emit("on_graph_structure", {"user_message": text})

    def emit_chat_model_end(
        self,
        *,
        content: str = "",
        tool_calls: list[dict] | None = None,
    ) -> dict:
        """Mark the end of a model turn. `tool_calls` is the list the model
        emitted (each dict at minimum has `name`; optionally `input`).
        """
        return self.emit("on_chat_model_end", {
            "content": content,
            "tool_calls": tool_calls or [],
        })

    def emit_tool_start(self, *, tool: str, input: dict | None = None) -> dict:
        return self.emit("on_tool_start", {
            "tool": tool,
            "input": input or {},
        })

    def emit_tool_end(self, *, tool: str, output: Any) -> dict:
        """Emit a tool result. `output` is stringified (json) so the stepper
        can scan it for error markers — matches existing stepper behaviour.
        """
        if not isinstance(output, str):
            output = json.dumps(output, default=str)
        return self.emit("on_tool_end", {"tool": tool, "output": output})

    def emit_position_report(self, *, node_id: str, rationale: str) -> dict:
        """The new event type introduced by this package. Stepper extension
        (see replay/stepper.py changes) consumes it to drive `active_node`.
        """
        return self.emit("on_position_report", {
            "node_id": node_id,
            "rationale": rationale,
        })

    def emit_chain_end(self) -> dict:
        """Mark the run complete. Stepper appends a terminal frame on this."""
        return self.emit("on_chain_end", {"name": "LangGraph"})

    def emit_thread_resume(
        self,
        *,
        prior_message_count: int,
        prior_tool_calls: list[str] | None = None,
    ) -> dict:
        return self.emit("on_thread_resume", {
            "prior_message_count": prior_message_count,
            "prior_tool_calls": list(prior_tool_calls or []),
        })

    def emit_policy_update(
        self,
        *,
        prior_policy_version: str,
        prior_policy_sha: str,
        policy_version: str,
        policy_sha: str,
    ) -> dict:
        return self.emit("on_policy_update", {
            "prior_policy_version": prior_policy_version,
            "prior_policy_sha":     prior_policy_sha,
            "policy_version":       policy_version,
            "policy_sha":           policy_sha,
        })

    def emit_invocation_error(
        self,
        *,
        error_class: str,
        error_message: str,
    ) -> dict:
        return self.emit("on_invocation_error", {
            "error_class":   error_class,
            "error_message": error_message,
        })

    def emit_context_carry(
        self,
        *,
        system_prompt: str,
        prompt_sections: list[dict] | None = None,
        first_user_message: str = "",
    ) -> dict:
        """Capture the verbatim system prompt the agent READ at assembly.

        Naming note: 'context carry' here means "what the agent saw" — NOT
        the agent's own emitted working memory (which is a separate concept
        introduced in the carry/working_memory plan).
        """
        return self.emit("on_context_carry", {
            "system_prompt":       system_prompt,
            "system_prompt_bytes": len(system_prompt),
            "prompt_sections":     list(prompt_sections or []),
            "first_user_message":  first_user_message,
        })


# ───────────────────────────────────────────────────────────────────────────
# Convenience for callers that don't want to manage a writer instance
# ───────────────────────────────────────────────────────────────────────────

def emit_event(
    path: str,
    event_type: str,
    payload: dict[str, Any] | None = None,
    *,
    agent: str = "",
    run_id: str | None = None,
    policy_version: str | None = None,
    policy_sha: str | None = None,
) -> dict:
    """One-off emit without instantiating an EventWriter. Each call opens +
    closes the file, so use the writer class for hot paths.

    Notably does NOT emit the on_chain_start boundary — caller's responsibility.
    """
    record: dict[str, Any] = {
        "ts":            _now_iso(),
        "event":         event_type,
        "run_id":        run_id or uuid.uuid4().hex[:12],
        "agent":         agent,
    }
    record["invocation_id"] = record["run_id"]
    record["trace_id"]      = record["run_id"]
    if policy_version is not None:
        record["policy_version"] = policy_version
    if policy_sha is not None:
        record["policy_sha"] = policy_sha
    if payload:
        for k, v in payload.items():
            if k in {"run_id", "invocation_id", "trace_id", "agent", "event"}:
                continue
            record[k] = v
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, default=str) + "\n")
    return record
