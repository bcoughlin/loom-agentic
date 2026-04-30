"""Loom Eventlog — JSONL writer matching the format `replay/loader.py` reads.

Public API:
    from loom_agentic.eventlog import EventWriter, emit_event

    writer = EventWriter(
        path="runs/session_abc.jsonl",
        agent="kepler_director",
        policy_version="v1",
        policy_sha="7a3b9c12",
    )
    writer.emit_graph_structure(mermaid=policy.mermaid, tools=["dino_detect", ...])
    writer.emit_user_message("identify the character in this image")
    writer.emit_chat_model_end(content="Let me check the library", tool_calls=[...])
    writer.emit_position_report(node_id="detecting", rationale="dino first")
    writer.emit_tool_start(tool="dino_detect", input={"prompt": "face"})
    writer.emit_tool_end(tool="dino_detect", output={...})
    writer.emit_chain_end()

Event vocabulary matches what `replay/stepper.py` and `replay/mermaid_for_run.py`
already understand, plus the new `on_position_report` event introduced by this
package and consumed by the extended stepper.
"""

from .writer import EventWriter, emit_event

__all__ = ["EventWriter", "emit_event"]
