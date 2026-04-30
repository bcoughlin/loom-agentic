"""Load a .policy.mmd + .policy.yaml pair into a Policy object.

Search strategy: caller passes `search_dirs`; loader probes each dir for
`<name>.policy.mmd` and `<name>.policy.yaml`. First match wins.

Mermaid parsing reuses `loom_agentic.orchestrate.mermaid_parser` so the
syntax constraints stay identical between authored policies and orchestrated
graphs.
"""

from __future__ import annotations

import hashlib
import os
from typing import Any

import yaml

from ..orchestrate.mermaid_parser import MermaidParseError, parse_mermaid
from .model import EdgePrompt, Policy


class PolicyLoadError(ValueError):
    """Raised on any policy load / validation failure."""


def load_policy(name: str, search_dirs: list[str]) -> Policy:
    """Load `<name>.policy.mmd` + `<name>.policy.yaml` from the first
    `search_dirs` entry that contains both. Returns a validated Policy.

    Raises:
      PolicyLoadError: file missing, mermaid invalid, yaml malformed, or
                       yaml references a node not in the mermaid.
    """
    if not search_dirs:
        raise PolicyLoadError("search_dirs is empty — pass at least one dir")

    mmd_path, yaml_path = _find_files(name, search_dirs)
    mermaid_bytes = _read_bytes(mmd_path)
    yaml_text = _read_text(yaml_path)

    # Parse + validate the mermaid; reuse orchestrate's parser so authored
    # policies share the same syntax surface as orchestrated graphs.
    try:
        graph = parse_mermaid(mermaid_bytes.decode("utf-8"))
    except MermaidParseError as e:
        raise PolicyLoadError(f"mermaid parse failed for {mmd_path}: {e}") from e

    # Parse YAML — empty yaml is valid (just version required, but we'll
    # surface a clearer error if version is missing).
    try:
        raw_yaml: dict[str, Any] = yaml.safe_load(yaml_text) or {}
    except yaml.YAMLError as e:
        raise PolicyLoadError(f"yaml parse failed for {yaml_path}: {e}") from e

    if not isinstance(raw_yaml, dict):
        raise PolicyLoadError(
            f"yaml at {yaml_path} must be a mapping at top level (got "
            f"{type(raw_yaml).__name__})"
        )

    version = raw_yaml.get("version")
    if not version or not isinstance(version, str):
        raise PolicyLoadError(
            f"yaml at {yaml_path} missing required string field 'version'"
        )

    # Globals — list of strings. Tolerate missing / empty.
    globals_raw = raw_yaml.get("globals") or []
    if not isinstance(globals_raw, list) or any(not isinstance(g, str) for g in globals_raw):
        raise PolicyLoadError(f"yaml 'globals' must be a list of strings ({yaml_path})")

    # Node prompts — yaml keys MUST exist in the mermaid. Catches typos.
    nodes_yaml = raw_yaml.get("nodes") or {}
    if not isinstance(nodes_yaml, dict):
        raise PolicyLoadError(f"yaml 'nodes' must be a mapping ({yaml_path})")

    node_prompts: dict[str, str] = {}
    for nid, body in nodes_yaml.items():
        if nid not in graph.nodes:
            raise PolicyLoadError(
                f"yaml references node '{nid}' which is not in {mmd_path}. "
                f"Known nodes: {sorted(graph.nodes.keys())}"
            )
        if not isinstance(body, dict):
            raise PolicyLoadError(
                f"yaml node '{nid}' must be a mapping with at least a 'prompt' field"
            )
        prompt = body.get("prompt")
        if prompt is not None:
            if not isinstance(prompt, str):
                raise PolicyLoadError(
                    f"yaml node '{nid}'.prompt must be a string"
                )
            node_prompts[nid] = prompt.rstrip()

    # Edge prompts — keys are "src->dst", values carry prompt + optional when.
    edges_yaml = raw_yaml.get("edges") or {}
    if not isinstance(edges_yaml, dict):
        raise PolicyLoadError(f"yaml 'edges' must be a mapping ({yaml_path})")

    edge_prompts: list[EdgePrompt] = []
    edge_pairs = {(e.source, e.target) for e in graph.edges}
    for key, body in edges_yaml.items():
        src, dst = _parse_edge_key(key, yaml_path)
        if (src, dst) not in edge_pairs:
            raise PolicyLoadError(
                f"yaml references edge '{key}' which is not in {mmd_path}. "
                f"Known edges: {sorted(f'{s}->{t}' for s, t in edge_pairs)}"
            )
        if not isinstance(body, dict):
            raise PolicyLoadError(
                f"yaml edge '{key}' must be a mapping"
            )
        prompt = body.get("prompt") or ""
        when = body.get("when")
        if when is not None and not isinstance(when, str):
            raise PolicyLoadError(f"yaml edge '{key}'.when must be a string")
        if not isinstance(prompt, str):
            raise PolicyLoadError(f"yaml edge '{key}'.prompt must be a string")
        edge_prompts.append(EdgePrompt(
            source=src, target=dst, when=when, prompt=prompt.rstrip(),
        ))

    # Node ids in declaration order — orchestrate's parser preserves insertion
    # order in the dict, so dict() iteration gives us declaration order.
    node_ids = tuple(graph.nodes.keys())

    sha = _compute_sha(mermaid_bytes)

    return Policy(
        name=name,
        version=version,
        sha=sha,
        mermaid=mermaid_bytes.decode("utf-8"),
        globals=tuple(globals_raw),
        node_ids=node_ids,
        node_prompts=node_prompts,
        edge_prompts=tuple(edge_prompts),
        raw_yaml=raw_yaml,
    )


# ───────────────────────────────────────────────────────────────────────────
# Helpers
# ───────────────────────────────────────────────────────────────────────────

def _find_files(name: str, search_dirs: list[str]) -> tuple[str, str]:
    """Return (mmd_path, yaml_path) from the first dir containing both.

    Both files must live in the same directory — finding only one is an error
    even if a sibling dir has the other.
    """
    expected_mmd = f"{name}.policy.mmd"
    expected_yaml = f"{name}.policy.yaml"
    tried: list[str] = []
    for d in search_dirs:
        mmd = os.path.join(d, expected_mmd)
        yml = os.path.join(d, expected_yaml)
        tried.append(d)
        if os.path.isfile(mmd) and os.path.isfile(yml):
            return mmd, yml
        # Detect partial matches early — usually a typo in one filename
        if os.path.isfile(mmd) and not os.path.isfile(yml):
            raise PolicyLoadError(
                f"found {mmd} but missing {yml} — both files must be present in the same dir"
            )
        if os.path.isfile(yml) and not os.path.isfile(mmd):
            raise PolicyLoadError(
                f"found {yml} but missing {mmd} — both files must be present in the same dir"
            )
    raise PolicyLoadError(
        f"policy '{name}' not found. Searched: {tried}. "
        f"Expected files: {expected_mmd} + {expected_yaml}"
    )


def _read_bytes(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def _read_text(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def _compute_sha(mermaid_bytes: bytes) -> str:
    return hashlib.sha256(mermaid_bytes).hexdigest()[:8]


def _parse_edge_key(key: str, yaml_path: str) -> tuple[str, str]:
    """Parse 'src->dst' or 'src -> dst' into (src, dst)."""
    if not isinstance(key, str) or "->" not in key:
        raise PolicyLoadError(
            f"yaml edge key {key!r} must be of form 'src->dst' (in {yaml_path})"
        )
    parts = [p.strip() for p in key.split("->", 1)]
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise PolicyLoadError(
            f"yaml edge key {key!r} malformed — expected 'src->dst'"
        )
    return parts[0], parts[1]
