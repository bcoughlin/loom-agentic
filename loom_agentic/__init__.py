"""Loom Agentic — visual agent orchestration + observability for LangGraph.

Three modes:
  1. Orchestrate — Mermaid blueprint -> LangGraph graph   [loom_agentic.orchestrate]
  2. Plugin      — drop into an existing LangGraph        [future]
  3. Temporal Replay — UI over stored run artifacts       [loom_agentic.replay]

Top-level deliberately imports nothing — `orchestrate` needs langgraph, `replay`
only needs boto3 (optional, for S3 loading). Consumers pick the submodule they need:

    from loom_agentic.orchestrate import build_from_mermaid    # needs langgraph
    from loom_agentic.replay      import frames_for_run        # no langgraph
"""

__version__ = "0.0.1"

__all__ = ["__version__"]
