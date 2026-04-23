"""Load JSONL event streams for replay.

Accepts either a local file path, an `s3://bucket/prefix` URI, or a list of
already-parsed event dicts. Groups events by `run_id` so each run is a
self-contained stream ready for the stepper.

The loader is deliberately minimal: no filtering, no enrichment. That
happens in `stepper.py`.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable
from dataclasses import dataclass, field
from urllib.parse import urlparse


@dataclass
class Run:
    """A single agent run — all events sharing the same `run_id`."""
    run_id:     str
    agent:     str
    started_at: str           # ISO timestamp of the first event
    ended_at:   str           # ISO timestamp of the last event
    events:     list[dict]    = field(default_factory=list)
    thread_id:  str = ""      # LangGraph thread_id when available (grouping key for siblings)

    @property
    def duration_ms(self) -> int:
        """Best-effort duration. 0 if either endpoint is missing."""
        if not self.started_at or not self.ended_at:
            return 0
        try:
            from datetime import datetime
            a = datetime.fromisoformat(self.started_at.replace("Z", "+00:00"))
            b = datetime.fromisoformat(self.ended_at.replace("Z", "+00:00"))
            return int((b - a).total_seconds() * 1000)
        except Exception:
            return 0


def load_events(source) -> list[dict]:
    """Load raw JSONL events from a file path, s3:// URI, or iterable.

    Keeps events as plain dicts so downstream code doesn't depend on a
    particular event schema — LangGraph event shapes evolve and we want
    the replayer tolerant of version drift.
    """
    if isinstance(source, list):
        return list(source)
    if isinstance(source, str):
        if source.startswith("s3://"):
            return _load_s3(source)
        return _load_file(source)
    if hasattr(source, "read"):  # file-like
        return [json.loads(line) for line in source if line.strip()]
    raise TypeError(f"unsupported event source: {type(source).__name__}")


def group_by_run(events: list[dict]) -> list[Run]:
    """Bucket raw events into Run objects (one per LangGraph invocation).

    LangGraph assigns a fresh `run_id` to every nested Runnable, so grouping
    by raw `run_id` produces hundreds of micro-runs per user invocation.
    What we actually want is one run per *top-level graph invocation*.

    Strategy:
      1. If events carry `invocation_id` (new tracing format, captured from
         `parent_ids`), group by that.
      2. Otherwise fall back to walking events in timestamp order, opening a
         new invocation bucket whenever we see `on_chain_start name=LangGraph`
         (or the event count for an invocation reaches a safety cap).

    Both paths produce the same shape — a list of Runs sorted newest-first.
    """
    # Sort all events globally by timestamp so fallback segmentation works
    events = sorted(events, key=lambda e: e.get("ts", ""))

    has_invocation_id = any(e.get("invocation_id") for e in events)

    buckets: dict[str, list[dict]] = {}
    if has_invocation_id:
        # Preferred path — trust the tracing layer. Synthetic events
        # (on_graph_structure, on_thread_resume, on_invocation_error)
        # are emitted outside the real LangGraph stream, so they lack
        # invocation_id. Attach each synthetic to the NEXT real event
        # sharing its trace_id — not the first-ever seen. Time-first
        # matching matters because primary + enforcement share a
        # thread_id (and therefore trace_id), and the same thread lives
        # across multiple turns hours apart. A global first-seen map
        # would glue every synthetic to the oldest invocation forever.
        synthetic_idxs: list[int] = []
        assigned: list[str | None] = [None] * len(events)
        for i, ev in enumerate(events):
            iid = ev.get("invocation_id")
            if iid:
                assigned[i] = iid
            else:
                synthetic_idxs.append(i)

        # Forward-scan: each synthetic picks the next real invocation
        # whose trace_id matches. Falls back to the nearest preceding
        # one if there's nothing after (synthetic at the tail end).
        for i in synthetic_idxs:
            tid = events[i].get("trace_id") or ""
            chosen: str | None = None
            for j in range(i + 1, len(events)):
                if assigned[j] and (events[j].get("trace_id") or "") == tid:
                    chosen = assigned[j]; break
            if chosen is None:
                for j in range(i - 1, -1, -1):
                    if assigned[j] and (events[j].get("trace_id") or "") == tid:
                        chosen = assigned[j]; break
            assigned[i] = chosen

        for i, ev in enumerate(events):
            key = assigned[i] or ev.get("run_id") or ""
            if not key:
                continue
            buckets.setdefault(key, []).append(ev)
    else:
        # Fallback — segment by LangGraph boundary events
        current_key: str | None = None
        for ev in events:
            is_graph_start = (
                ev.get("event") == "on_chain_start"
                and ev.get("name") == "LangGraph"
            )
            if is_graph_start:
                current_key = ev.get("run_id") or f"synthetic-{ev.get('ts','')}"
            if current_key is None:
                # Pre-start orphan events — bucket by their own run_id so nothing's lost
                current_key = ev.get("run_id") or f"orphan-{ev.get('ts','')}"
            buckets.setdefault(current_key, []).append(ev)
            if ev.get("event") == "on_chain_end" and ev.get("name") == "LangGraph":
                current_key = None

    raw_runs: list[Run] = []
    for run_id, evs in buckets.items():
        evs.sort(key=lambda e: e.get("ts", ""))
        agent = next((e.get("agent") for e in evs if e.get("agent")), "")
        started_at = evs[0].get("ts", "") if evs else ""
        ended_at   = evs[-1].get("ts", "") if evs else ""
        thread_id = next(
            (e.get("thread_id") for e in evs if e.get("thread_id")),
            next((e.get("trace_id") for e in evs if e.get("trace_id")), ""),
        )
        raw_runs.append(Run(
            run_id=run_id, agent=agent,
            started_at=started_at, ended_at=ended_at,
            events=evs,
            thread_id=thread_id or "",
        ))

    # Collapse by thread_id. One thread = one Loom entry, full stop.
    # Every invocation on that thread (primary, enforcement, turn 2,
    # turn 3, ...) contributes its events to the same run's timeline.
    # Turn boundaries remain visible inside via the user-message
    # frames and resume markers.
    runs = _group_by_thread(raw_runs)
    runs.sort(key=lambda r: r.started_at, reverse=True)
    return runs


def _group_by_thread(runs: list[Run]) -> list[Run]:
    """Merge all runs sharing a thread_id into one Run per thread.

    Uses the EARLIEST run_id on the thread as canonical (stable across
    future turns — when the same user hits the same screenshot again
    tomorrow, the thread's run_id doesn't change).

    Runs with no thread_id pass through unchanged — they're orphans
    with nothing to group against.
    """
    by_thread: dict[str, Run] = {}
    ungrouped: list[Run] = []

    for r in sorted(runs, key=lambda x: (x.started_at or "", x.run_id or "")):
        tid = r.thread_id or ""
        if not tid:
            ungrouped.append(r)
            continue
        existing = by_thread.get(tid)
        if existing is None:
            by_thread[tid] = r
        else:
            existing.events = sorted(
                existing.events + r.events,
                key=lambda e: e.get("ts", ""),
            )
            if (r.ended_at or "") > (existing.ended_at or ""):
                existing.ended_at = r.ended_at
            # started_at stays at the earliest — guaranteed by sort order

    return list(by_thread.values()) + ungrouped


# ───────────────────────────────────────────────────────────────────────────
# Source adapters
# ───────────────────────────────────────────────────────────────────────────

def _load_file(path: str) -> list[dict]:
    """Load a single JSONL file from disk."""
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def _load_s3(uri: str) -> list[dict]:
    """Load one or more JSONL objects from S3.

    If the URI points at a single `.jsonl` object, load that file. Otherwise
    treat it as a prefix and load every `.jsonl` object underneath.

    Requires boto3 (lazy-imported so the rest of loom_agentic works without it).
    """
    import boto3

    parsed = urlparse(uri)
    bucket = parsed.netloc
    key    = parsed.path.lstrip("/")
    if not bucket:
        raise ValueError(f"malformed s3 uri: {uri}")

    s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    events: list[dict] = []

    if key.endswith(".jsonl"):
        resp = s3.get_object(Bucket=bucket, Key=key)
        for line in resp["Body"].read().decode("utf-8", errors="replace").splitlines():
            if line.strip():
                events.append(json.loads(line))
        return events

    # Prefix scan
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=key):
        for obj in page.get("Contents", []):
            k = obj["Key"]
            if not k.endswith(".jsonl"):
                continue
            try:
                resp = s3.get_object(Bucket=bucket, Key=k)
                for line in resp["Body"].read().decode("utf-8", errors="replace").splitlines():
                    if line.strip():
                        events.append(json.loads(line))
            except Exception:
                # Robust over strict — one corrupt file shouldn't kill a replay listing.
                continue
    return events
