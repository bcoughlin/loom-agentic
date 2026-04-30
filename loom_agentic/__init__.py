"""Loom Agentic — visual agent orchestration + observability for LangGraph.

Four modes (as of v0.0.2):
  1. Orchestrate — Mermaid blueprint -> LangGraph graph   [loom_agentic.orchestrate]
  2. Policy      — authored .mmd + .yaml -> renderable Policy + report_position
                                                          [loom_agentic.policy]
  3. Eventlog    — JSONL writer matching the replay format
                                                          [loom_agentic.eventlog]
  4. Temporal Replay — UI over stored run artifacts       [loom_agentic.replay]

Top-level deliberately imports nothing — `orchestrate` needs langgraph,
`policy` needs pyyaml, `replay` only needs boto3 (optional, for S3 loading).
Consumers pick the submodule they need:

    from loom_agentic.orchestrate import build_from_mermaid    # needs langgraph
    from loom_agentic.policy      import load_policy           # needs pyyaml
    from loom_agentic.eventlog    import EventWriter           # stdlib only
    from loom_agentic.replay      import frames_for_run        # no langgraph
"""

__version__ = "0.0.2"

__all__ = ["__version__"]
