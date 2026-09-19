# Encyclopedia UI v1 (Knowledge Core)

Lightweight reuse of Sophia Knowledge Dashboard v2 **patterns** without porting the React runtime.

## Reused concepts (not code)

| Sophia v2 concept | AMI Encyclopedia v1 |
|-------------------|------------------------|
| Lazy graph loading | `/api/graph?root=&depth=` expands batch → source → revision → chunk |
| Semantic zoom | UI zoom in/out adjusts `depth` and graph root |
| Global search | `/api/search` across sources, claims, entities, chunks |
| Inspector panel | Right-side `/api/inspect/{kind}/{id}` with breadcrumb chain |
| Code↔Vision Bridge Matrix | **Evidence/Reality Matrix** via `/api/reality-matrix` |

## Evidence path (target UX)

`search → claim/source → inspector chain → chunk → revision → source`

## Security

Read-only API, loopback/Tailscale deployment only (see `DEPLOYMENT_SOPHIA_CORE.md`).

