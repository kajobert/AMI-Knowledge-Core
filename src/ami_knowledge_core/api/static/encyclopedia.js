const workspace = document.getElementById("workspace");
const inspectorBody = document.getElementById("inspector-body");
const inspectorChain = document.getElementById("inspector-chain");
const inspectorSubtitle = document.getElementById("inspector-subtitle");
const healthEl = document.getElementById("health");
const BASE_PATH = window.__AMI_KC_BASE__ || "";

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function safeJson(value) {
  return escapeHtml(JSON.stringify(value, null, 2));
}

const state = {
  view: "matrix",
  graphRoot: "batch:archaeology_batch_001",
  graphDepth: 1,
  selection: null,
};

async function api(path) {
  const response = await fetch(`${BASE_PATH}${path}`);
  if (!response.ok) {
    throw new Error(`${path} → HTTP ${response.status}`);
  }
  return response.json();
}

function badge(status) {
  return `<span class="badge badge-${escapeHtml(status)}">${escapeHtml(status)}</span>`;
}

function renderInspectorFromInspect(payload) {
  inspectorSubtitle.textContent = `${payload.kind} · ${payload.id}`;
  inspectorChain.innerHTML = (payload.chain || [])
    .map(
      (step) =>
        `<button type="button" data-inspect="${escapeHtml(step.kind)}:${escapeHtml(step.id)}">${escapeHtml(step.kind)}: ${escapeHtml(step.label)}</button>`
    )
    .join("");
  inspectorChain.querySelectorAll("[data-inspect]").forEach((button) => {
    button.addEventListener("click", () => {
      const [kind, id] = button.dataset.inspect.split(":");
      openInspector(kind, id);
    });
  });
  inspectorBody.innerHTML = `<pre>${safeJson(payload.record)}</pre>`;
}

async function openInspector(kind, id) {
  state.selection = { kind, id };
  const payload = await api(`/api/inspect/${kind}/${encodeURIComponent(id)}`);
  renderInspectorFromInspect(payload);
}

async function openFromSearchHit(kind, id) {
  await openInspector(kind, id);
  if (kind === "claim") {
    state.graphRoot = `chunk:${(await api(`/api/claims/${id}`)).evidence[0]?.chunk_id || id}`;
    state.graphDepth = 2;
  } else if (kind === "source") {
    state.graphRoot = `source:${id}`;
    state.graphDepth = 1;
  } else if (kind === "chunk") {
    state.graphRoot = `chunk:${id}`;
    state.graphDepth = 2;
  }
}

async function renderMatrix() {
  const rows = await api("/api/reality-matrix?batch_id=archaeology_batch_001");
  workspace.innerHTML = `
    <h2>Evidence / Reality Matrix</h2>
    <p class="muted">Historical design ↔ implementation status ↔ lifecycle ↔ supporting evidence</p>
    <table class="matrix-table">
      <thead>
        <tr>
          <th>Source</th>
          <th>Historical design</th>
          <th>Current implementation</th>
          <th>Matrix status</th>
          <th>Evidence</th>
        </tr>
      </thead>
      <tbody>
        ${rows
          .map(
            (row) => `
          <tr class="clickable" data-source="${escapeHtml(row.source_id)}">
            <td><strong>${escapeHtml(row.slug)}</strong><div class="muted">${escapeHtml(row.lifecycle_status)}</div></td>
            <td>${escapeHtml(row.historical_design)}</td>
            <td>${escapeHtml(row.current_implementation)}</td>
            <td>${badge(row.matrix_status)}</td>
            <td class="muted">${
              (row.supporting_evidence || [])
                .slice(0, 2)
                .map((ev) => escapeHtml(ev.excerpt?.slice(0, 80) || ev.chunk_id))
                .join("<br/>") || "—"
            }</td>
          </tr>`
          )
          .join("")}
      </tbody>
    </table>`;

  workspace.querySelectorAll("[data-source]").forEach((row) => {
    row.addEventListener("click", async () => {
      const sourceId = row.dataset.source;
      await openInspector("source", sourceId);
      state.graphRoot = `source:${sourceId}`;
      state.graphDepth = 2;
    });
  });
}

async function renderGraph() {
  const graph = await api(
    `/api/graph?root=${encodeURIComponent(state.graphRoot)}&depth=${state.graphDepth}`
  );
  workspace.innerHTML = `
    <div class="graph-shell">
      <div class="zoom-controls">
        <span class="muted">Semantic zoom</span>
        <button type="button" id="zoom-out">− Zoom out</button>
        <button type="button" id="zoom-in">+ Zoom in</button>
        <span class="muted">root: ${escapeHtml(graph.root)} · level ${escapeHtml(graph.zoom)}</span>
      </div>
      <div class="graph-canvas" id="graph-canvas"></div>
    </div>`;

  const canvas = document.getElementById("graph-canvas");
  for (const node of graph.nodes) {
    const el = document.createElement("article");
    el.className = "graph-node";
    el.innerHTML = `<div class="kind">${escapeHtml(node.kind)}</div><strong>${escapeHtml(node.label)}</strong><div class="muted">${escapeHtml(node.title || "")}</div>`;
    el.addEventListener("click", async () => {
      const [kind, id] = node.id.split(":");
      await openInspector(kind, id);
      if (node.expandable) {
        state.graphRoot = node.id;
        state.graphDepth = kind === "source" ? 2 : kind === "batch" ? 1 : 2;
        await renderGraph();
      }
    });
    canvas.appendChild(el);
  }

  document.getElementById("zoom-out").onclick = async () => {
    if (state.graphRoot.startsWith("chunk:")) {
      const chunk = await api(`/api/inspect/chunk/${state.graphRoot.split(":")[1]}`);
      state.graphRoot = `source:${chunk.record.source_id}`;
      state.graphDepth = 1;
    } else if (state.graphRoot.startsWith("source:")) {
      state.graphRoot = "batch:archaeology_batch_001";
      state.graphDepth = 0;
    }
    await renderGraph();
  };
  document.getElementById("zoom-in").onclick = async () => {
    state.graphDepth = Math.min(3, state.graphDepth + 1);
    await renderGraph();
  };
}

async function renderSources() {
  const sources = await api("/api/sources");
  workspace.innerHTML = `<h2>Sources</h2>${sources
    .map(
      (s) => `
      <article class="card clickable" data-source="${escapeHtml(s.source_id)}">
        <strong>${escapeHtml(s.title)}</strong>
        <div class="muted">${escapeHtml(s.slug)} · ${escapeHtml(s.lifecycle_status)} · ${escapeHtml(s.implementation_status)}</div>
      </article>`
    )
    .join("")}`;
  workspace.querySelectorAll("[data-source]").forEach((card) => {
    card.addEventListener("click", () => openInspector("source", card.dataset.source));
  });
}

async function renderClaims() {
  const claims = await api("/api/claims");
  const demoNote =
    "<p class='muted'>Preview uses sanitized archaeology fixtures only. Claims appear after worker extraction; absence of real private archaeology is expected until host ingest.</p>";
  workspace.innerHTML = `<h2>Claims</h2>${demoNote}${
    claims.length
      ? claims
          .map(
            (c) => `
      <article class="card clickable" data-claim="${escapeHtml(c.claim_id)}">
        <div>${escapeHtml(c.claim_text)}</div>
        <div class="muted">${escapeHtml(c.validation_status)} · ${escapeHtml(c.lifecycle_status)}</div>
      </article>`
          )
          .join("")
      : "<p class='muted'>No claims yet — matrix and search still work from sources/chunks.</p>"
  }`;
  workspace.querySelectorAll("[data-claim]").forEach((card) => {
    card.addEventListener("click", () => openFromSearchHit("claim", card.dataset.claim));
  });
}

async function renderTimeline() {
  const events = await api("/api/timeline");
  workspace.innerHTML = `<h2>Timeline</h2><pre>${safeJson(events)}</pre>`;
}

async function renderWorkerStatus() {
  const [status, jobs, ingestRuns] = await Promise.all([
    api("/api/worker/status"),
    api("/api/worker/jobs?limit=20"),
    api("/api/ingest/runs"),
  ]);
  workspace.innerHTML = `
    <h2>Continuous Archaeology Worker</h2>
    <p class="muted">Per-source checkpoints · no auto-canonical promotion</p>
    <h3>Job states</h3>
    <pre>${safeJson(status.jobs_by_state)}</pre>
    <h3>Recent worker runs</h3>
    <pre>${safeJson(status.recent_runs)}</pre>
    <h3>Recent jobs</h3>
    <pre>${safeJson(jobs)}</pre>
    <h3>Ingest runs</h3>
    <pre>${safeJson(ingestRuns)}</pre>`;
}

async function renderSearchResults(query) {
  const results = await api(`/api/search?q=${encodeURIComponent(query)}`);
  workspace.innerHTML = `
    <div class="search-results">
      <h2>Search: ${escapeHtml(query)}</h2>
      ${["sources", "claims", "entities", "chunks"]
        .map((section) => {
          const items = results[section] || [];
          return `<section><h3>${escapeHtml(section)} (${items.length})</h3>${items
            .map((item) => {
              const kind = section.slice(0, -1);
              const id =
                item.source_id || item.claim_id || item.entity_id || item.chunk_id;
              const label =
                item.title || item.claim_text || item.name || item.excerpt || id;
              return `<article class="card clickable" data-kind="${escapeHtml(kind)}" data-id="${escapeHtml(id)}">${escapeHtml(label)}</article>`;
            })
            .join("")}</section>`;
        })
        .join("")}
    </div>`;
  workspace.querySelectorAll("[data-kind]").forEach((card) => {
    card.addEventListener("click", () => openFromSearchHit(card.dataset.kind, card.dataset.id));
  });
}

async function renderView() {
  if (state.view === "matrix") await renderMatrix();
  if (state.view === "graph") await renderGraph();
  if (state.view === "sources") await renderSources();
  if (state.view === "claims") await renderClaims();
  if (state.view === "timeline") await renderTimeline();
  if (state.view === "worker") await renderWorkerStatus();
}

document.querySelectorAll("#sidebar button").forEach((button) => {
  button.addEventListener("click", async () => {
    document.querySelectorAll("#sidebar button").forEach((b) => b.classList.remove("active"));
    button.classList.add("active");
    state.view = button.dataset.view;
    await renderView();
  });
});

document.getElementById("global-search").addEventListener("submit", async (event) => {
  event.preventDefault();
  const query = document.getElementById("search-input").value.trim();
  if (!query) return;
  await renderSearchResults(query);
});

(async () => {
  try {
    const health = await api("/health");
    healthEl.textContent = `Health OK · pgvector ${health.pgvector}`;
  } catch (error) {
    healthEl.textContent = `Health failed: ${error.message}`;
  }
  await renderView();
})();
