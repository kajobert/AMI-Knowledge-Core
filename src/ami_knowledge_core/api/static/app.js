const panel = document.getElementById("panel");
const health = document.getElementById("health");

async function api(path) {
  const response = await fetch(path);
  if (!response.ok) {
    throw new Error(`${path} -> ${response.status}`);
  }
  return response.json();
}

function render(title, html) {
  panel.innerHTML = `<h2>${title}</h2>${html}`;
}

function card(item, body) {
  return `<article class="card">${body}</article>`;
}

async function showHome() {
  const runs = await api("/api/ingest/runs");
  const rows = runs
    .map(
      (run) =>
        card(
          run,
          `<strong>${run.ingest_run_id}</strong><div class="muted">${run.status} · ${run.started_at || ""}</div><pre>${JSON.stringify(run.stats, null, 2)}</pre>`
        )
    )
    .join("");
  render("Ingestion status", rows || "<p class='muted'>No ingest runs yet.</p>");
}

async function showSources(filter) {
  const query = filter === "current" ? "?current=true" : filter === "historical" ? "?current=false" : "";
  const sources = await api(`/api/sources${query}`);
  const rows = sources
    .map(
      (s) =>
        card(
          s,
          `<a href="#" data-source="${s.source_id}"><strong>${s.title}</strong></a>
           <div class="muted">${s.slug} · ${s.lifecycle_status} · ${s.implementation_status}</div>`
        )
    )
    .join("");
  render("Sources", rows || "<p class='muted'>No sources.</p>");
  panel.querySelectorAll("[data-source]").forEach((el) => {
    el.addEventListener("click", async (event) => {
      event.preventDefault();
      await showSourceDetail(el.dataset.source);
    });
  });
}

async function showSourceDetail(sourceId) {
  const detail = await api(`/api/sources/${sourceId}`);
  const s = detail.source;
  render(
    s.title,
    `<div class="muted">${s.source_id}</div>
     <p>Hash revisions: ${detail.revisions.map((r) => r.content_sha256).join(", ") || "—"}</p>
     <h3>Provenance / acquisitions</h3>
     <pre>${JSON.stringify(detail.acquisitions, null, 2)}</pre>
     <h3>Claims extracted</h3>
     <pre>${JSON.stringify(detail.claims, null, 2)}</pre>`
  );
}

async function showSearch() {
  render(
    "Search",
    `<label>Query <input id="q" type="search" /></label>
     <button id="go">Search chunks</button>
     <div id="results"></div>`
  );
  document.getElementById("go").onclick = async () => {
    const q = document.getElementById("q").value.trim();
    if (!q) return;
    const results = await api(`/api/chunks/search?q=${encodeURIComponent(q)}`);
    document.getElementById("results").innerHTML = results
      .map(
        (row) =>
          card(
            row,
            `<strong>${row.chunk_id}</strong><div class="muted">rank ${row.rank}</div><pre>${row.excerpt}</pre>`
          )
      )
      .join("");
  };
}

async function showClaims(filter) {
  const query = filter === "current" ? "?current=true" : filter === "historical" ? "?current=false" : "";
  const claims = await api(`/api/claims${query}`);
  const rows = claims
    .map(
      (c) =>
        card(
          c,
          `<a href="#" data-claim="${c.claim_id}">${c.claim_text}</a>
           <div class="muted">${c.validation_status} · ${c.lifecycle_status}</div>`
        )
    )
    .join("");
  render("Claims", rows || "<p class='muted'>No claims yet.</p>");
  panel.querySelectorAll("[data-claim]").forEach((el) => {
    el.addEventListener("click", async (event) => {
      event.preventDefault();
      await showClaimDetail(el.dataset.claim);
    });
  });
}

async function showClaimDetail(claimId) {
  const detail = await api(`/api/claims/${claimId}`);
  render(
    "Claim detail",
    `<pre>${JSON.stringify(detail.claim, null, 2)}</pre>
     <h3>Evidence chain (claim → chunk → source → revision)</h3>
     <pre>${JSON.stringify(detail.evidence, null, 2)}</pre>`
  );
}

async function showEntities(filter) {
  const query = filter === "current" ? "?current=true" : filter === "historical" ? "?current=false" : "";
  const entities = await api(`/api/entities${query}`);
  render(
    "Concepts / Entities",
    entities.length
      ? `<pre>${JSON.stringify(entities, null, 2)}</pre>`
      : "<p class='muted'>No entities ingested in v0 fixture.</p>"
  );
}

async function showTimeline() {
  const events = await api("/api/timeline");
  render("Timeline", `<pre>${JSON.stringify(events, null, 2)}</pre>`);
}

async function showConflicts() {
  const conflicts = await api("/api/conflicts");
  render("Conflicts", `<pre>${JSON.stringify(conflicts, null, 2)}</pre>`);
}

async function showPlaceholder(name) {
  render(name, "<p class='muted'>Slice v0 placeholder — wired via API in next iteration.</p>");
}

const views = {
  home: showHome,
  search: showSearch,
  sources: () => showSources(),
  entities: () => showEntities(),
  claims: () => showClaims(),
  components: () => showPlaceholder("Components"),
  decisions: () => showPlaceholder("Decisions"),
  timeline: showTimeline,
  current: () => showSources("current"),
  historical: () => showSources("historical"),
  conflicts: showConflicts,
  evidence: () => showPlaceholder("Evidence browser"),
};

document.querySelectorAll("#nav button").forEach((button) => {
  button.addEventListener("click", async () => {
    document.querySelectorAll("#nav button").forEach((b) => b.classList.remove("active"));
    button.classList.add("active");
    const view = views[button.dataset.view];
    if (view) await view();
  });
});

(async () => {
  try {
    const status = await api("/health");
    health.textContent = `Health: ${status.status} · pgvector ${status.pgvector}`;
  } catch (error) {
    health.textContent = `Health check failed: ${error.message}`;
  }
  document.querySelector('[data-view="home"]').click();
})();

