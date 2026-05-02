import { jsx, jsxs } from "react/jsx-runtime";
import { useRef, useState, useMemo, useEffect } from "react";
import mermaid from "mermaid";
import { useLocation, Link } from "react-router-dom";
function LoomPlayer({ run, onReload }) {
  var _a, _b, _c, _d, _e;
  const graphRef = useRef(null);
  const [cursor, setCursor] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [rendered, setRendered] = useState(false);
  const [liveMs, setLiveMs] = useState(0);
  const [snippetNode, setSnippetNode] = useState(null);
  const [contextOpen, setContextOpen] = useState(false);
  const [copiedKey, setCopiedKey] = useState(null);
  const mapsRef = useRef({ nodes: /* @__PURE__ */ new Map(), edges: /* @__PURE__ */ new Map() });
  const playAnchorRef = useRef(null);
  const frames = (run == null ? void 0 : run.frames) || [];
  const atEnd = cursor >= frames.length - 1;
  const positionByFrame = useMemo(() => {
    var _a2, _b2, _c2;
    const out = [];
    let reported = null;
    let inferred = null;
    for (const f of frames) {
      const kind = f.kind;
      if (kind === "on_tool_start" && f.tool_name === "report_position") {
        reported = {
          node: ((_a2 = f.tool_args) == null ? void 0 : _a2.node_id) || null,
          rationale: ((_b2 = f.tool_args) == null ? void 0 : _b2.rationale) || ((_c2 = f.tool_args) == null ? void 0 : _c2.note) || ""
        };
      } else if (kind === "on_tool_start" && f.tool_name) {
        inferred = f.tool_name;
      }
      out.push(
        (reported == null ? void 0 : reported.node) ? { kind: "reported", node: reported.node, rationale: reported.rationale } : inferred ? { kind: "inferred", node: inferred, rationale: "" } : null
      );
      if (kind === "on_chat_model_end") {
        reported = null;
      }
    }
    return out;
  }, [frames]);
  const position = positionByFrame[cursor] || null;
  const elapsedAtCursor = frames[0] && frames[cursor] ? Math.max(0, deltaMs(frames[0].ts, frames[cursor].ts)) : 0;
  const totalMs = frames[0] && frames.length > 1 ? Math.max(0, deltaMs(frames[0].ts, frames[frames.length - 1].ts)) : 0;
  useEffect(() => {
    mermaid.initialize({
      startOnLoad: false,
      theme: "dark",
      securityLevel: "loose",
      // useMaxWidth:false → SVG renders at its natural size (text stays
      // readable); the .graph container scrolls if the diagram is wider
      // than the viewport. Default `true` shrinks the whole thing to fit.
      flowchart: { curve: "basis", useMaxWidth: false, htmlLabels: true }
    });
  }, []);
  useEffect(() => {
    if (!(run == null ? void 0 : run.mermaid) || !graphRef.current) return;
    setRendered(false);
    setCursor(0);
    mermaid.render(`loom-${run.run_id}`, run.mermaid).then(({ svg }) => {
      graphRef.current.innerHTML = svg;
      buildMaps();
      setRendered(true);
    }).catch((err) => {
      graphRef.current.innerHTML = `<div style="color:#f87171;padding:16px">Mermaid render failed: ${err.message}</div>`;
    });
  }, [run == null ? void 0 : run.run_id]);
  useEffect(() => {
    if (!rendered) return;
    const frame = frames[cursor];
    if (!frame) return;
    clearHighlights();
    if ((run == null ? void 0 : run.policy) && position) {
      const cls = position.kind === "reported" ? "loom-active-node" : position.kind === "inferred" ? "loom-inferred-node" : "loom-mismatch-node";
      const el = mapsRef.current.nodes.get(position.node);
      if (el) {
        el.classList.add(cls);
        scrollNodeIntoView(el);
        const next = frames[cursor + 1];
        const fillMs = playing && position.kind === "reported" ? Math.max(200, deltaMs(frame.ts, next == null ? void 0 : next.ts)) : 0;
        if (fillMs) applyProgressFill(el, fillMs);
      }
      return;
    }
    if (frame.active_node) {
      const el = mapsRef.current.nodes.get(frame.active_node);
      if (el) {
        el.classList.add("loom-active-node");
        scrollNodeIntoView(el);
        const next = frames[cursor + 1];
        const fillMs = playing ? Math.max(200, deltaMs(frame.ts, next == null ? void 0 : next.ts)) : 0;
        applyProgressFill(el, fillMs);
      }
    }
    if (frame.active_edge) {
      const key = `${frame.active_edge[0]}>${frame.active_edge[1]}`;
      const el = mapsRef.current.edges.get(key);
      if (el) {
        el.classList.add("loom-active-edge");
        highlightArrowhead(el);
      }
    }
  }, [cursor, rendered, playing, position, run == null ? void 0 : run.policy]);
  function highlightArrowhead(edgeEl) {
    try {
      const ref = edgeEl.getAttribute && edgeEl.getAttribute("marker-end");
      if (!ref) return;
      const m = ref.match(/url\(#(.+?)\)/);
      if (!m) return;
      const origId = m[1];
      const greenId = `${origId}--loom-green`;
      let greenMarker = graphRef.current.querySelector(`[id="${greenId}"]`);
      if (!greenMarker) {
        const orig = graphRef.current.querySelector(`[id="${origId}"]`);
        if (!orig) return;
        greenMarker = orig.cloneNode(true);
        greenMarker.setAttribute("id", greenId);
        greenMarker.querySelectorAll("path, polygon, line, circle").forEach((el) => {
          el.setAttribute("stroke", "#22c55e");
          el.setAttribute("fill", "#22c55e");
        });
        orig.parentNode.appendChild(greenMarker);
      }
      edgeEl.dataset.loomOrigMarker = ref;
      edgeEl.setAttribute("marker-end", `url(#${greenId})`);
    } catch {
    }
  }
  function scrollNodeIntoView(nodeEl) {
    if (!graphRef.current || !nodeEl) return;
    try {
      const host = graphRef.current;
      const hostRect = host.getBoundingClientRect();
      const nodeRect = nodeEl.getBoundingClientRect();
      const margin = 40;
      let targetLeft = host.scrollLeft;
      let targetTop = host.scrollTop;
      if (nodeRect.left < hostRect.left + margin) {
        targetLeft += nodeRect.left - hostRect.left - margin;
      } else if (nodeRect.right > hostRect.right - margin) {
        targetLeft += nodeRect.right - hostRect.right + margin;
      }
      if (nodeRect.top < hostRect.top + margin) {
        targetTop += nodeRect.top - hostRect.top - margin;
      } else if (nodeRect.bottom > hostRect.bottom - margin) {
        targetTop += nodeRect.bottom - hostRect.bottom + margin;
      }
      host.scrollTo({ left: targetLeft, top: targetTop, behavior: "smooth" });
    } catch {
    }
  }
  useEffect(() => {
    if (!playing) return;
    if (cursor >= frames.length - 1) {
      setPlaying(false);
      return;
    }
    const here = frames[cursor];
    const next = frames[cursor + 1];
    const dtMs = deltaMs(here == null ? void 0 : here.ts, next == null ? void 0 : next.ts);
    const wait = Math.max(60, dtMs);
    const timer = setTimeout(() => setCursor((c) => c + 1), wait);
    return () => clearTimeout(timer);
  }, [playing, cursor, frames.length]);
  useEffect(() => {
    if (!playing) {
      setLiveMs(elapsedAtCursor);
      playAnchorRef.current = null;
      return;
    }
    playAnchorRef.current = { wallMs: Date.now(), elapsedMs: elapsedAtCursor };
    setLiveMs(elapsedAtCursor);
    const iv = setInterval(() => {
      const a = playAnchorRef.current;
      if (!a) return;
      setLiveMs(a.elapsedMs + (Date.now() - a.wallMs));
    }, 60);
    return () => clearInterval(iv);
  }, [playing, cursor]);
  function buildMaps() {
    var _a2;
    const nodes = /* @__PURE__ */ new Map(), edges = /* @__PURE__ */ new Map();
    graphRef.current.querySelectorAll("g.node").forEach((g) => {
      var _a3, _b2, _c2;
      let id = null;
      if ((_a3 = g.dataset) == null ? void 0 : _a3.id) id = g.dataset.id;
      if (!id && g.id) {
        const patterns = [
          /-flowchart-(.+?)(?:-\d+)?$/,
          // mermaid 11 rendered id
          /^flowchart-(?:v2-)?(.+?)-\d+$/,
          // mermaid 10
          /^node-(.+?)-\d+$/
        ];
        for (const p of patterns) {
          const m = g.id.match(p);
          if (m) {
            id = m[1];
            break;
          }
        }
      }
      if (!id) {
        const text = (_c2 = (_b2 = g.querySelector(".nodeLabel, span.nodeLabel, foreignObject p, text")) == null ? void 0 : _b2.textContent) == null ? void 0 : _c2.trim();
        if (text) id = text;
      }
      if (id) nodes.set(id, g);
    });
    const edgeSelectors = [
      "g.edgePaths > g",
      "g.edgePath",
      "path.flowchart-link",
      "g.edgePaths path"
    ];
    const nodeIdSet = new Set(nodes.keys());
    graphRef.current.querySelectorAll(edgeSelectors.join(",")).forEach((el) => {
      var _a3;
      const cls = el.getAttribute && el.getAttribute("class") || ((_a3 = el.className) == null ? void 0 : _a3.baseVal) || el.className || "";
      if (typeof cls === "string") {
        const s = cls.match(/\bLS-(\S+)/);
        const t = cls.match(/\bLE-(\S+)/);
        if (s && t) {
          edges.set(`${s[1]}>${t[1]}`, el);
          return;
        }
      }
      const id = el.id || "";
      const tail = id.includes("L_") ? id.slice(id.lastIndexOf("L_") + 2) : "";
      if (!tail) return;
      const parts = tail.split("_");
      const trailingNumeric = /^\d+$/.test(parts[parts.length - 1]);
      const usable = trailingNumeric ? parts.slice(0, -1) : parts;
      for (let i = 1; i < usable.length; i++) {
        const src = usable.slice(0, i).join("_");
        const dst = usable.slice(i).join("_");
        if (nodeIdSet.has(src) && nodeIdSet.has(dst)) {
          edges.set(`${src}>${dst}`, el);
          return;
        }
      }
    });
    mapsRef.current = { nodes, edges };
    if ((_a2 = run == null ? void 0 : run.policy) == null ? void 0 : _a2.nodes) {
      for (const [nodeId, el] of nodes.entries()) {
        if (!run.policy.nodes[nodeId]) continue;
        el.style.cursor = "pointer";
        el.addEventListener("click", (ev) => {
          ev.stopPropagation();
          setSnippetNode(nodeId);
        });
      }
    }
    const wantedNodes = new Set(frames.map((f) => f.active_node).filter(Boolean));
    const wantedEdges = new Set(frames.map((f) => f.active_edge && `${f.active_edge[0]}>${f.active_edge[1]}`).filter(Boolean));
    const matchedNodes = [...wantedNodes].filter((n) => nodes.has(n));
    const matchedEdges = [...wantedEdges].filter((e) => edges.has(e));
    console.groupCollapsed("[Loom] SVG map");
    console.log("SVG nodes found:", [...nodes.keys()]);
    console.log("SVG edges found:", [...edges.keys()]);
    console.log("Frames want highlight on nodes:", [...wantedNodes]);
    console.log("Frames want highlight on edges:", [...wantedEdges]);
    console.log(`Node matches: ${matchedNodes.length}/${wantedNodes.size}`, matchedNodes.length < wantedNodes.size ? "⚠️" : "✓");
    console.log(`Edge matches: ${matchedEdges.length}/${wantedEdges.size}`, matchedEdges.length < wantedEdges.size ? "⚠️" : "✓");
    const firstNodeG = graphRef.current.querySelector("g.node");
    if (firstNodeG) console.log("First node SVG:", firstNodeG.outerHTML.slice(0, 500));
    const firstEdge = graphRef.current.querySelector("g.edgePaths > g, g.edgePath, path.flowchart-link, g.edgePaths path");
    if (firstEdge) console.log("First edge SVG:", firstEdge.outerHTML.slice(0, 500));
    console.groupEnd();
  }
  function clearHighlights() {
    mapsRef.current.nodes.forEach((el) => {
      var _a2, _b2;
      el.classList.remove("loom-active-node");
      el.classList.remove("loom-inferred-node");
      el.classList.remove("loom-mismatch-node");
      const fill = el.querySelector(".loom-progress-fill");
      if (fill) {
        const clipId = (_a2 = fill.dataset) == null ? void 0 : _a2.clipId;
        if (clipId) {
          const clip = (_b2 = graphRef.current) == null ? void 0 : _b2.querySelector(`#${clipId}`);
          if (clip) clip.remove();
        }
        fill.remove();
      }
    });
    mapsRef.current.edges.forEach((el) => el.classList.remove("loom-active-edge"));
    if (graphRef.current) {
      graphRef.current.querySelectorAll("[data-loom-orig-marker]").forEach((el) => {
        el.setAttribute("marker-end", el.dataset.loomOrigMarker);
        delete el.dataset.loomOrigMarker;
      });
    }
  }
  function applyProgressFill(nodeEl, durationMs) {
    const bg = nodeEl.querySelector("path, rect, polygon, circle");
    if (!bg || typeof bg.getBBox !== "function") return;
    let bbox;
    try {
      bbox = bg.getBBox();
    } catch {
      return;
    }
    const ns = "http://www.w3.org/2000/svg";
    const svg = nodeEl.ownerSVGElement;
    let defs = svg == null ? void 0 : svg.querySelector(":scope > defs");
    if (!defs && svg) {
      defs = document.createElementNS(ns, "defs");
      svg.insertBefore(defs, svg.firstChild);
    }
    const clipId = `loom-clip-${Math.random().toString(36).slice(2, 9)}`;
    let clip;
    if (defs) {
      clip = document.createElementNS(ns, "clipPath");
      clip.setAttribute("id", clipId);
      const clone = bg.cloneNode(true);
      clone.removeAttribute("style");
      clone.removeAttribute("class");
      clone.removeAttribute("filter");
      clip.appendChild(clone);
      defs.appendChild(clip);
    }
    const overlay = document.createElementNS(ns, "rect");
    overlay.setAttribute("class", "loom-progress-fill");
    overlay.setAttribute("x", bbox.x);
    overlay.setAttribute("y", bbox.y);
    overlay.setAttribute("width", 0);
    overlay.setAttribute("height", bbox.height);
    if (clip) {
      overlay.setAttribute("clip-path", `url(#${clipId})`);
      overlay.dataset.clipId = clipId;
    } else {
      overlay.setAttribute("rx", 6);
      overlay.setAttribute("ry", 6);
    }
    overlay.style.fill = "rgba(34, 197, 94, 0.28)";
    overlay.style.pointerEvents = "none";
    overlay.style.transition = `width ${durationMs}ms linear`;
    bg.parentNode.insertBefore(overlay, bg.nextSibling);
    requestAnimationFrame(() => {
      overlay.setAttribute("width", bbox.width);
    });
  }
  function seek(i) {
    setCursor(Math.max(0, Math.min(frames.length - 1, i)));
  }
  if (!run) {
    return /* @__PURE__ */ jsx("div", { style: styles$1.empty, children: "Select a run to replay." });
  }
  return /* @__PURE__ */ jsxs("div", { style: styles$1.root, children: [
    /* @__PURE__ */ jsx("style", { children: highlightCSS }),
    /* @__PURE__ */ jsxs("div", { style: styles$1.header, children: [
      /* @__PURE__ */ jsx("span", { style: styles$1.title, children: run.agent || "agent" }),
      /* @__PURE__ */ jsxs("span", { style: styles$1.meta, children: [
        (_a = run.run_id) == null ? void 0 : _a.slice(0, 8),
        " · ",
        frames.length,
        " frames · ",
        run.duration_ms || 0,
        "ms · started ",
        formatTs(run.started_at)
      ] }),
      run.context && /* @__PURE__ */ jsxs(
        "button",
        {
          onClick: () => setContextOpen((o) => !o),
          style: contextOpen ? styles$1.contextBtnActive : styles$1.contextBtn,
          title: "Show the system prompt the agent read at turn start",
          children: [
            "Context · ",
            formatBytes(run.context.system_prompt_bytes)
          ]
        }
      )
    ] }),
    /* @__PURE__ */ jsxs("div", { style: styles$1.body, children: [
      /* @__PURE__ */ jsxs("div", { style: styles$1.graphWrapper, children: [
        /* @__PURE__ */ jsx("div", { ref: graphRef, className: "loom-graph", style: styles$1.graph, children: "Rendering…" }),
        onReload && /* @__PURE__ */ jsx(
          "button",
          {
            onClick: onReload,
            title: "Reload this run from the server",
            style: styles$1.reloadBtn,
            children: "↻"
          }
        ),
        (((_b = run == null ? void 0 : run.run_policy) == null ? void 0 : _b.version) || ((_c = run == null ? void 0 : run.policy) == null ? void 0 : _c.version)) && (() => {
          var _a2, _b2, _c2;
          const stripAgent = (v) => (v || "").replace(/^[^@]+@/, "");
          const declared = stripAgent(((_a2 = run.policy) == null ? void 0 : _a2.version) || ((_b2 = run.run_policy) == null ? void 0 : _b2.version)) || "?";
          const current = stripAgent((_c2 = run.run_policy) == null ? void 0 : _c2.version) || declared;
          const match = current === declared;
          return /* @__PURE__ */ jsxs(
            "div",
            {
              style: match ? styles$1.versionPillMatch : styles$1.versionPillMismatch,
              title: match ? `Authored policy and this run agree (${declared})` : `Authored policy is ${declared}; this run ran under ${current}. A future turn on this thread will upgrade.`,
              children: [
                /* @__PURE__ */ jsx("span", { style: styles$1.versionPillLabel, children: "POLICY" }),
                /* @__PURE__ */ jsxs("span", { style: styles$1.versionPillText, children: [
                  /* @__PURE__ */ jsx("span", { style: styles$1.versionPillDeclared, children: declared }),
                  " / ",
                  /* @__PURE__ */ jsx("span", { style: styles$1.versionPillCurrent, children: current })
                ] })
              ]
            }
          );
        })(),
        rendered && (position == null ? void 0 : position.rationale) && /* @__PURE__ */ jsxs("div", { style: styles$1.rationaleBubble, title: "Agent's rationale for the current node", children: [
          /* @__PURE__ */ jsx("div", { style: styles$1.rationaleLabel, children: "rationale" }),
          /* @__PURE__ */ jsx("div", { style: styles$1.rationaleText, children: position.rationale })
        ] }),
        rendered && frames.length > 0 && /* @__PURE__ */ jsxs("div", { style: styles$1.timerRow, title: "Elapsed / total run time", children: [
          /* @__PURE__ */ jsx("span", { style: styles$1.timer, children: formatElapsed(liveMs) }),
          /* @__PURE__ */ jsxs("span", { style: styles$1.timerTotal, children: [
            "/ ",
            formatElapsed(totalMs)
          ] }),
          /* @__PURE__ */ jsxs(
            "span",
            {
              style: !position ? styles$1.posPillEmpty : position.kind === "reported" ? styles$1.posPillReported : styles$1.posPillInferred,
              title: !position ? "No report_position called and no tool call to infer from" : position.kind === "reported" ? `Agent reported position: ${position.node}` : `No report_position for this turn — inferred from tool: ${position.node}`,
              children: [
                /* @__PURE__ */ jsx("span", { style: styles$1.posDot, children: "◉" }),
                /* @__PURE__ */ jsx("span", { style: styles$1.posLabel, children: !position ? "not reported" : position.kind === "inferred" ? `(inferred) ${position.node}` : position.node })
              ]
            }
          )
        ] })
      ] }),
      /* @__PURE__ */ jsx("div", { style: styles$1.log, children: frames.map((f, i) => {
        var _a2, _b2;
        const active = i === cursor;
        const rationale = ((_a2 = f.tool_args) == null ? void 0 : _a2.rationale) || ((_b2 = f.tool_args) == null ? void 0 : _b2.note) || "";
        const hasThought = !!(f.reply_text || rationale);
        const showFull = active || hasThought;
        return /* @__PURE__ */ jsxs(
          "div",
          {
            onClick: () => seek(i),
            style: {
              ...styles$1.logRow,
              ...f.rejected ? styles$1.logRowRejected : {},
              ...active ? styles$1.logRowActive : {}
            },
            children: [
              /* @__PURE__ */ jsxs("div", { style: styles$1.logTs, children: [
                formatTs(f.ts),
                " · #",
                i + 1,
                f.rejected && /* @__PURE__ */ jsx("span", { style: styles$1.logRowRejectedBadge, children: " · course-corrected" })
              ] }),
              /* @__PURE__ */ jsx("div", { style: showFull ? styles$1.logSummaryFull : styles$1.logSummary, children: f.summary }),
              rationale && /* @__PURE__ */ jsxs("div", { style: styles$1.logRationale, title: "Agent's rationale for this step", children: [
                /* @__PURE__ */ jsx("span", { style: styles$1.logRationaleLabel, children: "why:" }),
                " ",
                rationale
              ] })
            ]
          },
          i
        );
      }) })
    ] }),
    /* @__PURE__ */ jsxs("div", { style: styles$1.controls, children: [
      /* @__PURE__ */ jsx("button", { onClick: () => seek(cursor - 1), disabled: cursor === 0, style: styles$1.btn, children: "◀ Prev" }),
      /* @__PURE__ */ jsx(
        "button",
        {
          onClick: () => {
            if (atEnd) {
              setCursor(0);
              setPlaying(true);
              return;
            }
            setPlaying((p) => !p);
          },
          style: styles$1.btn,
          children: playing ? "⏸ Pause" : atEnd ? "↻ Replay" : "▶ Realtime"
        }
      ),
      /* @__PURE__ */ jsx("button", { onClick: () => seek(cursor + 1), disabled: atEnd, style: styles$1.btn, children: "Next ▶" }),
      /* @__PURE__ */ jsx(
        "input",
        {
          type: "range",
          min: "0",
          max: Math.max(0, frames.length - 1),
          value: cursor,
          onChange: (e) => seek(parseInt(e.target.value, 10)),
          style: styles$1.scrub
        }
      ),
      /* @__PURE__ */ jsxs("span", { style: styles$1.counter, children: [
        cursor + 1,
        " / ",
        frames.length
      ] })
    ] }),
    contextOpen && run.context && (() => {
      const ctx = run.context;
      const total = Math.max(1, ctx.system_prompt_bytes || 1);
      const sections = ctx.prompt_sections || [];
      const copy = (label, text) => {
        var _a2;
        (_a2 = navigator.clipboard) == null ? void 0 : _a2.writeText(text || "").then(() => {
          setCopiedKey(label);
          setTimeout(() => setCopiedKey((k) => k === label ? null : k), 1200);
        });
      };
      return /* @__PURE__ */ jsxs("div", { style: styles$1.contextDrawer, children: [
        /* @__PURE__ */ jsxs("div", { style: styles$1.snippetHeader, children: [
          /* @__PURE__ */ jsxs("span", { style: styles$1.snippetTitle, children: [
            "Context · ",
            /* @__PURE__ */ jsx("code", { style: styles$1.snippetCode, children: formatBytes(ctx.system_prompt_bytes) }),
            ctx.policy_version && /* @__PURE__ */ jsxs("span", { style: styles$1.snippetTool, children: [
              " — policy ",
              ctx.policy_version.replace(/^[^@]+@/, "")
            ] })
          ] }),
          /* @__PURE__ */ jsxs("div", { style: { display: "flex", gap: 6 }, children: [
            /* @__PURE__ */ jsx(
              "button",
              {
                onClick: () => copy("prompt", ctx.system_prompt),
                style: styles$1.contextCopyBtn,
                title: "Copy the full system prompt to the clipboard",
                children: copiedKey === "prompt" ? "✓ copied" : "Copy prompt"
              }
            ),
            /* @__PURE__ */ jsx("button", { onClick: () => setContextOpen(false), style: styles$1.snippetClose, children: "✕" })
          ] })
        ] }),
        sections.length > 0 && /* @__PURE__ */ jsx("div", { style: styles$1.sectionList, children: sections.map((s, i) => {
          const pct = Math.max(2, Math.round((s.bytes || 0) / total * 100));
          return /* @__PURE__ */ jsxs("div", { style: styles$1.sectionRow, children: [
            /* @__PURE__ */ jsxs("div", { style: styles$1.sectionRowTop, children: [
              /* @__PURE__ */ jsx("code", { style: styles$1.snippetCode, children: s.key }),
              /* @__PURE__ */ jsx("span", { style: styles$1.sectionBytes, children: formatBytes(s.bytes) })
            ] }),
            /* @__PURE__ */ jsx("div", { style: styles$1.sectionBar, children: /* @__PURE__ */ jsx("div", { style: { ...styles$1.sectionBarFill, width: `${pct}%` } }) })
          ] }, i);
        }) }),
        /* @__PURE__ */ jsx("pre", { style: styles$1.snippetBody, children: (ctx.system_prompt || "(empty)").trim() }),
        ctx.first_user_message && /* @__PURE__ */ jsxs("div", { style: styles$1.contextUserMsg, children: [
          /* @__PURE__ */ jsx("div", { style: styles$1.snippetEdgesTitle, children: "First user message" }),
          /* @__PURE__ */ jsx("pre", { style: styles$1.contextUserMsgBody, children: ctx.first_user_message })
        ] })
      ] });
    })(),
    snippetNode && ((_e = (_d = run == null ? void 0 : run.policy) == null ? void 0 : _d.nodes) == null ? void 0 : _e[snippetNode]) && /* @__PURE__ */ jsxs("div", { style: styles$1.snippetDrawer, children: [
      /* @__PURE__ */ jsxs("div", { style: styles$1.snippetHeader, children: [
        /* @__PURE__ */ jsxs("span", { style: styles$1.snippetTitle, children: [
          "Node: ",
          /* @__PURE__ */ jsx("code", { style: styles$1.snippetCode, children: snippetNode }),
          run.policy.nodes[snippetNode].tool && /* @__PURE__ */ jsxs("span", { style: styles$1.snippetTool, children: [
            " — fires ",
            /* @__PURE__ */ jsx("code", { style: styles$1.snippetCode, children: run.policy.nodes[snippetNode].tool })
          ] })
        ] }),
        /* @__PURE__ */ jsx("button", { onClick: () => setSnippetNode(null), style: styles$1.snippetClose, children: "✕" })
      ] }),
      /* @__PURE__ */ jsx("pre", { style: styles$1.snippetBody, children: (run.policy.nodes[snippetNode].prompt || "(no prompt authored)").trim() }),
      (() => {
        const outgoing = (run.policy.edges || []).filter((e) => e.source === snippetNode);
        if (!outgoing.length) return null;
        return /* @__PURE__ */ jsxs("div", { style: styles$1.snippetEdges, children: [
          /* @__PURE__ */ jsx("div", { style: styles$1.snippetEdgesTitle, children: "Outgoing edges" }),
          outgoing.map((e, i) => /* @__PURE__ */ jsxs("div", { style: styles$1.snippetEdgeRow, children: [
            /* @__PURE__ */ jsxs("span", { children: [
              "→ ",
              /* @__PURE__ */ jsx("code", { style: styles$1.snippetCode, children: e.target })
            ] }),
            e.when && /* @__PURE__ */ jsxs("div", { style: styles$1.snippetWhen, children: [
              /* @__PURE__ */ jsx("b", { children: "when:" }),
              " ",
              e.when
            ] })
          ] }, i))
        ] });
      })()
    ] })
  ] });
}
const highlightCSS = `
  /* Mermaid injects svg { max-width: 100% } which shrinks the
     flowchart to fit its container — makes wide flowcharts unreadable
     and blocks horizontal scroll. Force intrinsic sizing so the
     .graph div's overflow:auto can scroll both axes. */
  .loom-graph svg {
    max-width: none !important;
    width: auto !important;
    height: auto !important;
  }

  /* Active node: green outline + glow. The progress fill inside the node
     (a separate <rect class="loom-progress-fill">) carries the duration
     animation. */
  .loom-active-node rect,
  .loom-active-node polygon,
  .loom-active-node circle,
  .loom-active-node path,
  .loom-active-node > .node-bkg,
  .loom-active-node > .label-container {
    stroke: #22c55e !important;
    stroke-width: 3px !important;
    filter: drop-shadow(0 0 8px #22c55e);
  }
  /* Exempt the progress-fill rect from the outline rule so it stays a
     clean translucent fill, no stroke. */
  .loom-active-node .loom-progress-fill {
    stroke: none !important;
    filter: none !important;
  }
  /* Inferred node: yellow outline, dashed to convey low confidence. */
  .loom-inferred-node rect,
  .loom-inferred-node polygon,
  .loom-inferred-node circle,
  .loom-inferred-node path,
  .loom-inferred-node > .node-bkg,
  .loom-inferred-node > .label-container {
    stroke: #eab308 !important;
    stroke-width: 3px !important;
    stroke-dasharray: 6 4 !important;
    filter: drop-shadow(0 0 8px #eab308);
  }
  /* Mismatched / off-policy node: red outline. */
  .loom-mismatch-node rect,
  .loom-mismatch-node polygon,
  .loom-mismatch-node circle,
  .loom-mismatch-node path,
  .loom-mismatch-node > .node-bkg,
  .loom-mismatch-node > .label-container {
    stroke: #f87171 !important;
    stroke-width: 3px !important;
    filter: drop-shadow(0 0 8px #f87171);
  }
  /* Active edge: green */
  .loom-active-edge,
  .loom-active-edge path,
  path.loom-active-edge {
    stroke: #22c55e !important;
    stroke-width: 3px !important;
  }
  /* Arrowhead highlight is handled by swapping marker-end to a cloned
     green-fill marker at runtime (see highlightArrowhead). No CSS-based
     recoloring here — it would color every arrow since markers are
     shared in <defs>. */
`;
function formatTs(iso) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}:${String(d.getSeconds()).padStart(2, "0")}`;
  } catch {
    return iso;
  }
}
function deltaMs(a, b) {
  if (!a || !b) return 0;
  try {
    return new Date(b).getTime() - new Date(a).getTime();
  } catch {
    return 0;
  }
}
function formatElapsed(ms) {
  if (!ms || ms < 0) ms = 0;
  const m = Math.floor(ms / 6e4);
  const s = Math.floor(ms % 6e4 / 1e3);
  const t = Math.floor(ms % 1e3 / 100);
  return `${m}:${String(s).padStart(2, "0")}.${t}`;
}
function formatBytes(n) {
  if (!n || n <= 0) return "0 B";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(2)} MB`;
}
const styles$1 = {
  root: { display: "flex", flexDirection: "column", height: "100%", background: "#0e0e18", color: "#e8e8f0", fontFamily: "monospace" },
  header: { padding: "10px 16px", borderBottom: "1px solid #1e1e2e", display: "flex", alignItems: "baseline", gap: 12, flexShrink: 0 },
  title: { fontWeight: 600, color: "#c084fc" },
  meta: { color: "#666", fontSize: 12 },
  body: { flex: 1, display: "grid", gridTemplateColumns: "2fr 1fr", minHeight: 0 },
  // min-width: 0 is the magic grid hack: without it, a grid column
  // auto-sizes to its CONTENT (the mermaid SVG can be very wide),
  // which ignores the 2fr constraint and pushes the right column
  // (log + any absolutely-positioned drawer) off the viewport.
  graphWrapper: { position: "relative", minHeight: 0, minWidth: 0, overflow: "hidden" },
  graph: { padding: 16, overflow: "auto", width: "100%", height: "100%", boxSizing: "border-box" },
  timerRow: {
    position: "absolute",
    top: 12,
    right: 56,
    zIndex: 2,
    display: "flex",
    alignItems: "center",
    gap: 8,
    pointerEvents: "none"
  },
  reloadBtn: {
    position: "absolute",
    top: 12,
    right: 16,
    zIndex: 3,
    background: "#1a1a2e",
    color: "#c8c8d0",
    border: "1px solid #2a2a3e",
    width: 30,
    height: 30,
    borderRadius: 6,
    cursor: "pointer",
    fontFamily: "monospace",
    fontSize: 14,
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    boxShadow: "0 2px 8px rgba(0,0,0,0.4)"
  },
  timer: {
    background: "rgba(34, 197, 94, 0.15)",
    color: "#22c55e",
    border: "1px solid rgba(34, 197, 94, 0.4)",
    padding: "4px 10px",
    borderRadius: 6,
    fontFamily: "monospace",
    fontSize: 13,
    fontWeight: 600,
    fontVariantNumeric: "tabular-nums",
    boxShadow: "0 2px 8px rgba(0,0,0,0.4)"
  },
  timerTotal: {
    color: "#888",
    fontFamily: "monospace",
    fontSize: 12,
    fontWeight: 500,
    fontVariantNumeric: "tabular-nums"
  },
  posPillReported: {
    display: "inline-flex",
    alignItems: "center",
    gap: 6,
    background: "rgba(34, 197, 94, 0.15)",
    color: "#22c55e",
    border: "1px solid rgba(34, 197, 94, 0.4)",
    padding: "4px 10px",
    borderRadius: 6,
    fontFamily: "monospace",
    fontSize: 12,
    fontWeight: 600,
    boxShadow: "0 2px 8px rgba(0,0,0,0.4)",
    pointerEvents: "auto"
  },
  posPillEmpty: {
    display: "inline-flex",
    alignItems: "center",
    gap: 6,
    background: "rgba(120, 120, 130, 0.12)",
    color: "#888",
    border: "1px solid rgba(120, 120, 130, 0.3)",
    padding: "4px 10px",
    borderRadius: 6,
    fontFamily: "monospace",
    fontSize: 12,
    fontWeight: 500,
    boxShadow: "0 2px 8px rgba(0,0,0,0.4)",
    pointerEvents: "auto"
  },
  posPillInferred: {
    display: "inline-flex",
    alignItems: "center",
    gap: 6,
    background: "rgba(234, 179, 8, 0.15)",
    color: "#eab308",
    border: "1px dashed rgba(234, 179, 8, 0.5)",
    padding: "4px 10px",
    borderRadius: 6,
    fontFamily: "monospace",
    fontSize: 12,
    fontWeight: 600,
    boxShadow: "0 2px 8px rgba(0,0,0,0.4)",
    pointerEvents: "auto"
  },
  posDot: { fontSize: 10 },
  posLabel: { fontVariantNumeric: "tabular-nums" },
  snippetDrawer: {
    position: "absolute",
    bottom: 72,
    right: 16,
    width: 420,
    maxHeight: "60vh",
    background: "#0b0b14",
    border: "1px solid #2a2a3e",
    borderRadius: 8,
    boxShadow: "0 8px 24px rgba(0,0,0,0.6)",
    zIndex: 4,
    display: "flex",
    flexDirection: "column",
    overflow: "hidden"
  },
  snippetHeader: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    padding: "10px 12px",
    borderBottom: "1px solid #1e1e2e",
    background: "#13131f"
  },
  snippetTitle: { color: "#e8e8f0", fontSize: 12, fontFamily: "monospace" },
  snippetCode: {
    background: "#1a1a2e",
    padding: "1px 6px",
    borderRadius: 3,
    color: "#c084fc",
    fontSize: 11
  },
  snippetTool: { color: "#888", fontSize: 11 },
  snippetClose: {
    background: "none",
    border: "none",
    color: "#888",
    cursor: "pointer",
    fontSize: 14,
    padding: 0,
    width: 24,
    height: 24
  },
  snippetBody: {
    margin: 0,
    padding: 12,
    color: "#e8e8f0",
    fontSize: 12,
    lineHeight: 1.5,
    whiteSpace: "pre-wrap",
    wordBreak: "break-word",
    overflowY: "auto",
    background: "#0b0b14",
    fontFamily: "monospace"
  },
  snippetEdges: {
    borderTop: "1px solid #1e1e2e",
    padding: "8px 12px",
    background: "#13131f",
    maxHeight: 160,
    overflowY: "auto"
  },
  snippetEdgesTitle: {
    fontSize: 10,
    color: "#888",
    textTransform: "uppercase",
    letterSpacing: 0.5,
    marginBottom: 4
  },
  snippetEdgeRow: {
    fontSize: 11,
    color: "#c8c8d0",
    marginBottom: 8,
    fontFamily: "monospace"
  },
  snippetWhen: { color: "#888", marginTop: 2, fontSize: 11, fontWeight: 400 },
  versionPillMatch: {
    position: "absolute",
    top: 12,
    left: 16,
    zIndex: 3,
    display: "inline-flex",
    alignItems: "center",
    gap: 6,
    background: "rgba(34, 197, 94, 0.12)",
    color: "#22c55e",
    border: "1px solid rgba(34, 197, 94, 0.35)",
    padding: "4px 10px",
    borderRadius: 6,
    fontFamily: "monospace",
    fontSize: 12,
    fontWeight: 600,
    boxShadow: "0 2px 8px rgba(0,0,0,0.4)",
    pointerEvents: "auto"
  },
  versionPillMismatch: {
    position: "absolute",
    top: 12,
    left: 16,
    zIndex: 3,
    display: "inline-flex",
    alignItems: "center",
    gap: 6,
    background: "rgba(234, 179, 8, 0.12)",
    color: "#eab308",
    border: "1px dashed rgba(234, 179, 8, 0.5)",
    padding: "4px 10px",
    borderRadius: 6,
    fontFamily: "monospace",
    fontSize: 12,
    fontWeight: 600,
    boxShadow: "0 2px 8px rgba(0,0,0,0.4)",
    pointerEvents: "auto"
  },
  versionPillLabel: {
    fontSize: 9,
    color: "#888",
    textTransform: "uppercase",
    letterSpacing: 0.5,
    fontWeight: 500
  },
  versionPillText: { fontVariantNumeric: "tabular-nums" },
  versionPillCurrent: { fontWeight: 700 },
  versionPillDeclared: { opacity: 0.7 },
  rationaleBubble: {
    // Sits below the version pill so they stack on the left edge.
    position: "absolute",
    top: 52,
    left: 16,
    zIndex: 2,
    maxWidth: 360,
    background: "rgba(13, 16, 28, 0.92)",
    border: "1px solid #2a2a3e",
    borderRadius: 10,
    padding: "10px 12px",
    boxShadow: "0 6px 18px rgba(0,0,0,0.55)",
    pointerEvents: "auto",
    color: "#e8e8f0"
  },
  rationaleLabel: {
    fontSize: 9,
    fontFamily: "monospace",
    color: "#888",
    textTransform: "uppercase",
    letterSpacing: 0.6,
    marginBottom: 4
  },
  rationaleText: {
    fontSize: 12,
    lineHeight: 1.4,
    color: "#e8e8f0",
    fontStyle: "italic",
    whiteSpace: "pre-wrap",
    wordBreak: "break-word"
  },
  log: { borderLeft: "1px solid #1e1e2e", overflowY: "auto", display: "flex", flexDirection: "column" },
  // Muted left border on every row so the 3px active accent doesn't
  // cause content to jump horizontally between states.
  logRow: {
    padding: "8px 12px",
    borderBottom: "1px solid #1a1a2a",
    borderLeft: "3px solid #1e1e2e",
    cursor: "pointer",
    fontSize: 12,
    lineHeight: 1.4
  },
  logRowActive: { background: "#1a1a2e", borderLeft: "3px solid #c084fc" },
  // Rejected: a Loom enforcement primitive returned an off-policy
  // error. Dashed red border + muted-red tint distinguishes "agent
  // was course-corrected by Loom" from "tool crashed" (solid red
  // later via ❌ summary) and "tool succeeded" (default).
  logRowRejected: {
    borderLeft: "3px dashed #f87171",
    background: "rgba(248, 113, 113, 0.05)"
  },
  logRowRejectedBadge: {
    color: "#f87171",
    fontSize: 9,
    fontWeight: 600,
    textTransform: "uppercase",
    letterSpacing: 0.5
  },
  logTs: { color: "#666", fontSize: 10 },
  // Collapsed: single line with CSS ellipsis so long summaries don't
  // stretch the panel. Expanded (active row): same style, but wraps.
  logSummary: {
    color: "#e8e8f0",
    marginTop: 2,
    whiteSpace: "nowrap",
    overflow: "hidden",
    textOverflow: "ellipsis"
  },
  logSummaryFull: {
    color: "#e8e8f0",
    marginTop: 2,
    whiteSpace: "pre-wrap",
    wordBreak: "break-word"
  },
  logRationale: {
    color: "#a8a8c0",
    marginTop: 4,
    fontSize: 11,
    paddingLeft: 8,
    borderLeft: "2px solid #3a3a52",
    whiteSpace: "pre-wrap",
    wordBreak: "break-word"
  },
  logRationaleLabel: {
    color: "#7a7a92",
    fontSize: 10,
    textTransform: "uppercase",
    letterSpacing: 0.5,
    fontWeight: 600
  },
  controls: { borderTop: "1px solid #1e1e2e", padding: "10px 16px", display: "flex", gap: 12, alignItems: "center", background: "#0b0b14", flexShrink: 0 },
  btn: { background: "#1a1a2e", color: "#e8e8f0", border: "1px solid #1e1e2e", padding: "6px 12px", cursor: "pointer", fontFamily: "inherit", borderRadius: 4, fontSize: 12 },
  scrub: { flex: 1 },
  counter: { color: "#666", fontSize: 12, minWidth: 80, textAlign: "right" },
  empty: { color: "#555", padding: 40, textAlign: "center", fontSize: 13 },
  contextBtn: {
    marginLeft: "auto",
    background: "#1a1a2e",
    color: "#c8c8d0",
    border: "1px solid #2a2a3e",
    padding: "4px 10px",
    borderRadius: 4,
    cursor: "pointer",
    fontFamily: "monospace",
    fontSize: 11
  },
  contextBtnActive: {
    marginLeft: "auto",
    background: "rgba(192, 132, 252, 0.15)",
    color: "#c084fc",
    border: "1px solid rgba(192, 132, 252, 0.5)",
    padding: "4px 10px",
    borderRadius: 4,
    cursor: "pointer",
    fontFamily: "monospace",
    fontSize: 11
  },
  contextDrawer: {
    position: "absolute",
    bottom: 72,
    left: 16,
    width: 520,
    maxHeight: "72vh",
    background: "#0b0b14",
    border: "1px solid #2a2a3e",
    borderRadius: 8,
    boxShadow: "0 8px 24px rgba(0,0,0,0.6)",
    zIndex: 5,
    display: "flex",
    flexDirection: "column",
    overflow: "hidden"
  },
  contextCopyBtn: {
    background: "#1a1a2e",
    color: "#c8c8d0",
    border: "1px solid #2a2a3e",
    padding: "4px 10px",
    borderRadius: 4,
    cursor: "pointer",
    fontFamily: "monospace",
    fontSize: 11
  },
  sectionList: {
    borderBottom: "1px solid #1e1e2e",
    padding: "8px 12px",
    background: "#0f0f1a",
    maxHeight: 220,
    overflowY: "auto"
  },
  sectionRow: { marginBottom: 6 },
  sectionRowTop: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 3
  },
  sectionBytes: { color: "#888", fontSize: 11, fontVariantNumeric: "tabular-nums" },
  sectionBar: {
    height: 4,
    background: "#1a1a2e",
    borderRadius: 2,
    overflow: "hidden"
  },
  sectionBarFill: {
    height: "100%",
    background: "linear-gradient(90deg,#c084fc,#7c3aed)"
  },
  contextUserMsg: {
    borderTop: "1px solid #1e1e2e",
    padding: "8px 12px",
    background: "#13131f",
    maxHeight: 160,
    overflowY: "auto",
    flexShrink: 0
  },
  contextUserMsgBody: {
    margin: "4px 0 0",
    color: "#c8c8d0",
    fontSize: 11,
    whiteSpace: "pre-wrap",
    wordBreak: "break-word",
    fontFamily: "monospace"
  }
};
function AdminNav({ routes = [], wordmark = "LOOM", right }) {
  const { pathname } = useLocation();
  const normalized = pathname.replace(/\/$/, "") || "/";
  let activePath = null;
  let activeLen = -1;
  for (const r of routes) {
    const rp = r.path.replace(/\/$/, "") || "/";
    if (normalized === rp || normalized.startsWith(rp === "/" ? "/" : rp + "/")) {
      if (rp.length > activeLen) {
        activePath = r.path;
        activeLen = rp.length;
      }
    }
  }
  return /* @__PURE__ */ jsxs("div", { style: styles.bar, children: [
    /* @__PURE__ */ jsx("div", { style: styles.wordmark, children: wordmark }),
    /* @__PURE__ */ jsx("nav", { style: styles.nav, children: routes.map((r) => {
      const active = r.path === activePath;
      return /* @__PURE__ */ jsx(
        Link,
        {
          to: r.path,
          style: { ...styles.link, ...active ? styles.linkActive : {} },
          children: r.label
        },
        r.path
      );
    }) }),
    /* @__PURE__ */ jsx("div", { style: styles.right, children: right })
  ] });
}
const styles = {
  bar: {
    display: "flex",
    alignItems: "center",
    gap: 4,
    padding: "0 16px",
    height: 44,
    borderBottom: "1px solid #1e1e2e",
    background: "#111118",
    flexShrink: 0
  },
  wordmark: {
    fontWeight: 800,
    letterSpacing: 2,
    color: "#fff",
    fontSize: 13,
    marginRight: 12,
    whiteSpace: "nowrap"
  },
  nav: {
    display: "flex",
    alignItems: "center",
    gap: 2
  },
  link: {
    color: "#555",
    fontSize: 12,
    fontWeight: 600,
    textDecoration: "none",
    padding: "5px 10px",
    borderRadius: 6,
    transition: "color 0.12s, background 0.12s",
    whiteSpace: "nowrap"
  },
  linkActive: {
    color: "#e8e8f0",
    background: "#1e1e2e"
  },
  right: {
    marginLeft: "auto",
    fontSize: 12,
    color: "#555",
    whiteSpace: "nowrap"
  }
};
export {
  AdminNav,
  LoomPlayer
};
//# sourceMappingURL=loom-web.js.map
