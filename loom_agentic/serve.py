"""Loom web server — mounts the built React UI and serves replay JSON.

Usage:
    LOOM_EVENTLOG_PATH=/path/to/events.jsonl python -m loom_agentic.serve

    # Multiple eventlogs (e.g. one per agent):
    LOOM_EVENTLOG_PATH=/path/to/agents/*.jsonl python -m loom_agentic.serve

    # Bind to non-localhost (use behind a reverse proxy with auth):
    LOOM_BIND_HOST=0.0.0.0 python -m loom_agentic.serve

The server is intentionally simple — no auth, defaults to localhost.
Designed for developer/admin use. If exposed beyond localhost, the
consumer is responsible for fronting it with auth.

Two surface areas:
  /          — built React app (loom_agentic/web/dist/), if present
  /api/*     — JSON endpoints consumed by the React app

If web/dist/ doesn't exist, /  returns instructions to run the build.
The /api endpoints work either way.
"""

from __future__ import annotations

import glob
import os
import time
from pathlib import Path
from typing import Optional

try:
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
    from fastapi.staticfiles import StaticFiles
except ImportError as _e:
    raise ImportError(
        "loom_agentic.serve requires the 'web' extra: "
        "pip install 'loom-agentic[web]'  (or install fastapi + uvicorn directly)"
    ) from _e

from .replay import (
    Run,
    group_by_run,
    load_events,
    serialize_run,
    serialize_run_listing,
)


# ── Paths and config ────────────────────────────────────────────────────────
PKG_ROOT = Path(__file__).parent          # loom_agentic/loom_agentic/
REPO_ROOT = PKG_ROOT.parent               # loom_agentic/
WEB_DIST = REPO_ROOT / "web" / "dist"     # loom_agentic/web/dist/

EVENTLOG_PATH = os.environ.get("LOOM_EVENTLOG_PATH", "")
BIND_HOST = os.environ.get("LOOM_BIND_HOST", "127.0.0.1")
BIND_PORT = int(os.environ.get("LOOM_BIND_PORT", "5174"))


def _resolve_eventlog_paths() -> list[str]:
    """Expand LOOM_EVENTLOG_PATH glob patterns into a sorted file list.

    Single path or comma-separated list both work. Globs expand. Missing
    files return empty rather than erroring — the API surfaces "no runs"
    as a 200 response with empty list, not a 500.
    """
    if not EVENTLOG_PATH:
        return []
    patterns = [p.strip() for p in EVENTLOG_PATH.split(",") if p.strip()]
    out: list[str] = []
    for p in patterns:
        if any(c in p for c in "*?[]"):
            out.extend(sorted(glob.glob(p)))
        elif os.path.exists(p):
            out.append(p)
    return out


def _load_all_runs() -> list[Run]:
    """Read all configured eventlogs and group into runs.

    No caching for v1 — eventlog reads are fast enough at the volumes we
    care about (a few thousand events per file, a few files). If this
    becomes felt, add a TTL cache keyed on file mtime.
    """
    paths = _resolve_eventlog_paths()
    all_events: list[dict] = []
    for p in paths:
        try:
            all_events.extend(load_events(p))
        except Exception as e:
            print(f"[loom.serve] failed to load {p}: {type(e).__name__}: {e}", flush=True)
    return group_by_run(all_events)


# ── App ──────────────────────────────────────────────────────────────────────
app = FastAPI(title="Loom")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ── API endpoints ────────────────────────────────────────────────────────────
@app.get("/api/health")
def health():
    return {
        "ok": True,
        "eventlog_paths": _resolve_eventlog_paths(),
        "web_dist_built": WEB_DIST.exists(),
    }


@app.get("/api/runs")
def list_runs(hours: int = 24, agent: Optional[str] = None, limit: int = 200):
    """List runs from configured eventlogs.

    hours: only runs that started within the last N hours
    agent: filter by agent name
    limit: cap total returned (most recent first)
    """
    runs = _load_all_runs()
    if agent:
        runs = [r for r in runs if r.agent == agent]
    # Filter by start time. ISO-8601 strings sort lexicographically; we
    # subtract `hours` from now and string-compare.
    if hours > 0:
        cutoff = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(time.time() - hours * 3600))
        runs = [r for r in runs if (r.started_at or "") >= cutoff]
    # Most recent first
    runs.sort(key=lambda r: r.started_at or "", reverse=True)
    runs = runs[:limit]
    return {"runs": [serialize_run_listing(r) for r in runs], "count": len(runs)}


@app.get("/api/runs/{run_id}")
def get_run(run_id: str):
    runs = _load_all_runs()
    for r in runs:
        if r.run_id == run_id:
            return serialize_run(r)
    raise HTTPException(404, f"run {run_id!r} not found")


@app.get("/api/agents")
def list_agents():
    """Distinct agent names seen in the configured eventlogs.
    Used by the UI's agent filter dropdown."""
    runs = _load_all_runs()
    return {"agents": sorted({r.agent for r in runs if r.agent})}


# ── Static React app ─────────────────────────────────────────────────────────
# Mount LAST so /api routes take precedence. If dist/ doesn't exist, serve
# instructions instead of 404ing the root.

if WEB_DIST.exists():
    # SPA mount — serve assets directly, fall through to index.html for
    # client-side routes (BrowserRouter handles /replay, /sessions, etc.).
    @app.get("/")
    def root():
        return FileResponse(WEB_DIST / "index.html")

    # Catch-all for client-side routes — must come BEFORE the StaticFiles
    # mount so routes like /replay don't 404.
    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str):
        # Real assets live under /assets/* — let StaticFiles handle those
        # via the mount below. For any other path, return index.html and
        # let BrowserRouter take over.
        candidate = WEB_DIST / full_path
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(WEB_DIST / "index.html")

    app.mount("/assets", StaticFiles(directory=str(WEB_DIST / "assets")), name="assets")
else:
    @app.get("/")
    def root():
        msg = f"""
        <html><head><title>Loom — build needed</title>
        <style>body {{ font-family: monospace; background: #0e0e18; color: #e8e8f0; padding: 40px; line-height: 1.6; }}
        code {{ background: #1e1e2e; padding: 2px 6px; border-radius: 4px; }}
        </style></head><body>
        <h2 style="color: #c084fc">Loom — web UI not built</h2>
        <p>The React app at <code>{WEB_DIST}</code> hasn't been built yet.</p>
        <p>Run:</p>
        <pre>cd {REPO_ROOT}/web &amp;&amp; npm install &amp;&amp; npm run build</pre>
        <p>Or run the dev server in parallel:</p>
        <pre>cd {REPO_ROOT}/web &amp;&amp; npm run dev</pre>
        <p>API endpoints work without a build — try
        <a href="/api/health" style="color: #67e8f9">/api/health</a>.</p>
        </body></html>
        """
        return HTMLResponse(msg)


# ── Entry point ──────────────────────────────────────────────────────────────
def main():
    import uvicorn
    if not EVENTLOG_PATH:
        print("[loom.serve] WARNING: LOOM_EVENTLOG_PATH not set — /api/runs will return empty.", flush=True)
        print("[loom.serve] Set it to a JSONL path or glob, e.g.:", flush=True)
        print("[loom.serve]   LOOM_EVENTLOG_PATH=/path/to/events.jsonl python -m loom_agentic.serve", flush=True)
    print(f"[loom.serve] starting on http://{BIND_HOST}:{BIND_PORT}", flush=True)
    print(f"[loom.serve] eventlog paths: {_resolve_eventlog_paths() or '(none configured)'}", flush=True)
    print(f"[loom.serve] web dist: {WEB_DIST} ({'built' if WEB_DIST.exists() else 'not built'})", flush=True)
    uvicorn.run(app, host=BIND_HOST, port=BIND_PORT)


if __name__ == "__main__":
    main()
