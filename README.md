# weekend-k8s-lab

> A minimal end-to-end e-commerce slice — a **camera catalog** — built in one weekend to practise running a real polyglot application on a 3-node Kubernetes cluster.

**Live:** <https://k8sproject.limseongin.com>

The goal was not to ship a perfect product, but to wire up every layer of a small production-shaped stack — relational + document storage, a Python API, a React SPA, an in-cluster image registry, a private DNS-routed public endpoint — and feel each integration point in the body, before the same shape shows up in a longer team project.

---

## What it does

- Browse a catalog of ~50 cameras (`/`).
- Open a product to see its long-form description, specs, and reviews (`/products/:id`).
- Everything is read-only — there is no auth, no cart, no checkout. The point is the platform, not the feature surface.

Domain model and glossary live in [`CONTEXT.md`](./CONTEXT.md). Architectural choices are recorded as [ADRs](./docs/adr/).

---

## Architecture

```
                        Browser
                           │ https://k8sproject.limseongin.com
                           ▼
                   Cloudflare Edge
                  (DNS · TLS termination)
                           │
                outbound-initiated tunnel
                           ▼
 ┌──────────────────── Kubernetes (3-node, on-prem) ────────────────────┐
 │                                                                      │
 │   cloudflared Deployment                                             │
 │       │                                                              │
 │       ├─ /api/* ───────► backend  (FastAPI)                          │
 │       │                    │                                         │
 │       │                    ├── Postgres StatefulSet   (catalog)      │
 │       │                    └── MongoDB  StatefulSet   (detail +      │
 │       │                                                reviews)      │
 │       │                                                              │
 │       └─ /*     ───────► frontend (React + Vite + nginx)             │
 │                                                                      │
 │   in-cluster Docker Registry (image storage for the cluster)         │
 │                                                                      │
 └──────────────────────────────────────────────────────────────────────┘
```

- **Public ingress** is a Cloudflare Tunnel — the cluster has no public IP and opens no inbound ports. `cloudflared` initiates an outbound connection from inside the cluster to Cloudflare's edge, and Cloudflare routes the subdomain through that tunnel.
- **Two databases by design.** Postgres is the master record for catalog rows; MongoDB carries the variable-shape product detail and reviews. Rationale in [ADR 0001](./docs/adr/0001-postgres-master-mongo-supplement.md).
- **Stateful workloads** run as StatefulSets backed by hostPath PVs — fit for a lab, not for production. Rationale in [ADR 0002](./docs/adr/0002-databases-as-statefulsets-with-hostpath-pv.md).

---

## Tech stack

| Layer        | Choice                                                |
| ------------ | ----------------------------------------------------- |
| Frontend     | React 19 · Vite 6 · TypeScript · react-router 7       |
| Static serve | nginx (SPA fallback + `/api/*` proxy)                 |
| Backend      | Python 3 · FastAPI                                    |
| Catalog DB   | PostgreSQL (StatefulSet, hostPath PV)                 |
| Detail DB    | MongoDB (StatefulSet, hostPath PV)                    |
| Container    | Docker, pushed to in-cluster Registry                 |
| Manifests    | Kustomize (single `base/`)                            |
| Cluster      | kubeadm-installed Kubernetes on 3 Ubuntu VMs          |
| Public DNS   | Cloudflare Tunnel + Cloudflare DNS                    |

---

## Repository layout

```
weekend-k8s-lab/
├── backend/                       FastAPI service
│   ├── app/
│   │   ├── main.py                /api/products, /api/products/{id}, /healthz
│   │   └── seed_mongo.py          bootstraps detail + reviews from Postgres
│   ├── requirements.txt
│   └── Dockerfile
│
├── frontend/                      React + Vite SPA, served by nginx
│   ├── src/
│   │   ├── components/
│   │   │   ├── CameraIcon.tsx     inline SVG, no external image deps
│   │   │   └── Layout.tsx         sticky brand header + footer
│   │   ├── pages/
│   │   │   ├── Catalog.tsx        grid of products
│   │   │   └── ProductDetail.tsx  description, specs, reviews
│   │   ├── api.ts                 fetch wrappers
│   │   ├── types.ts
│   │   └── index.css              light/dark themed
│   ├── nginx.conf                 SPA fallback + /api/* → backend proxy
│   ├── package.json
│   └── Dockerfile
│
├── k8s/
│   └── base/                      kustomize base — single namespace
│       ├── namespace.yaml
│       ├── registry/              in-cluster Docker Registry
│       ├── postgres/              StatefulSet + seed Job + Secret
│       ├── mongo/                 StatefulSet + seed Job + Secret
│       ├── backend/               Deployment + Service
│       ├── frontend/              Deployment + Service
│       ├── cloudflared/           Tunnel daemon, public ingress
│       └── kustomization.yaml
│
├── docs/
│   ├── adr/                       Architecture Decision Records
│   ├── agents/                    AI-agent operating notes (issue tracker, labels, domain)
│   └── runbooks/                  step-by-step deploy procedures per component
│
├── CONTEXT.md                     ubiquitous-language glossary
├── CLAUDE.md                      AI-agent instructions for this repo
└── README.md
```

---

## Running it

The cluster setup itself (kubeadm install, containerd insecure-registry config, etc.) is captured in the runbooks. Once a cluster exists:

```bash
# 1. Bring up the platform (registry, both DBs, seed jobs)
kubectl apply -k k8s/base

# 2. Build and push application images to the in-cluster registry
cd backend  && docker build -t 192.168.56.105:30500/backend:vN  . && docker push 192.168.56.105:30500/backend:vN
cd frontend && docker build -t 192.168.56.105:30500/frontend:vN . && docker push 192.168.56.105:30500/frontend:vN

# 3. Bump the image tag in the respective k8s/base/<component>/deployment.yaml,
#    then re-apply
kubectl apply -k k8s/base
kubectl -n weekend-k8s-lab rollout status deploy/backend
kubectl -n weekend-k8s-lab rollout status deploy/frontend
```

For the public endpoint, see [`docs/runbooks/`](./docs/runbooks/) — `cloudflared` requires a one-time tunnel creation, a DNS route, and a `secrets.yaml` (template at [`k8s/base/cloudflared/secrets.example.yaml`](./k8s/base/cloudflared/secrets.example.yaml), gitignored once filled).

Component-specific runbooks:

- [`docs/runbooks/insecure-registry.md`](./docs/runbooks/insecure-registry.md)
- [`docs/runbooks/mongo-deploy.md`](./docs/runbooks/mongo-deploy.md)
- [`docs/runbooks/backend-build-and-deploy.md`](./docs/runbooks/backend-build-and-deploy.md)
- [`docs/runbooks/frontend-deploy.md`](./docs/runbooks/frontend-deploy.md)

---

## Build journal

The project was built across a weekend, issue by issue. Today's session closed out the last two — the frontend (`#6`) and the public ingress (`#2`) — and is recorded chronologically below so the trade-offs and dead ends are visible alongside the wins.

| # | Step | Notes |
| - | ---- | ----- |
| 1 | **Frontend `/api/*` proxy fix** | First browser load against the SPA produced `Unexpected token '<'` in JSON.parse — nginx had no proxy rule for `/api/*`, so the SPA fallback returned `index.html` for every API call. Added an explicit `location /api/ { proxy_pass http://backend:80; }` block ordered before the catch-all. |
| 2 | **Image bump `frontend:v1 → v2`** | `imagePullPolicy: IfNotPresent` was silently reusing the cached v1 layer on the nodes, so the fixed nginx.conf never shipped until the manifest's tag advanced. |
| 3 | **UI polish — Aperture shop look** | Dropped `loremflickr` (its `camera` keyword was returning landscapes and giraffes). Replaced per-product thumbnails with a single inline SVG camera icon so the catalog works offline and stays visually consistent. Added a `Layout` wrapper with a sticky brand header (*Aperture · Pro Cameras & Lenses*), promo bar, footer, and a polished card hover/shadow treatment. Detail page got a breadcrumb. Dark mode preserved via `prefers-color-scheme`. |
| 4 | **Image bump `frontend:v2 → v3`** | Required because the new shop-style UI needed to land in the cluster. |
| 5 | **Enable `cloudflared` in kustomization** | `cloudflared/` was committed earlier but gated out of the base kustomization until its `secrets.yaml` existed. Activated. |
| 6 | **Cloudflare Tunnel setup (manual)** | Registered `limseongin.com` in Cloudflare, repointed nameservers at the registrar, installed the `cloudflared` CLI on the master node, ran `cloudflared tunnel login` → `tunnel create k8sproject` → `tunnel route dns k8sproject k8sproject.limseongin.com`, and dropped the resulting credentials into a gitignored `secrets.yaml`. |
| 7 | **`cloudflared` distroless fix** | First apply crashed with `exec: "sh": executable file not found`. The 2024.12.2 image is distroless; the previous Deployment wrapped the binary in `sh -c …` to expand `$TUNNEL_ID`. Removed the wrapper, switched to direct `args:`, and bumped the image to `2026.5.0` (matching the host CLI). |
| 8 | **UUID positional fix** | The next crash was `"cloudflared tunnel run" requires the ID or name of the tunnel`. `--credentials-file` does **not** imply the UUID; `tunnel run` still needs it positionally. Kubernetes' native `$(VAR_NAME)` substitution in `args:` expands env vars before exec — no shell needed — so the UUID is now pulled from the Secret into `TUNNEL_ID` and inlined as `args: [..., run, $(TUNNEL_ID)]`. |
| 9 | **Subdomain live** | `https://k8sproject.limseongin.com` resolves through Cloudflare → tunnel → in-cluster `cloudflared` → `backend`/`frontend` Services. Full data path verified end-to-end from a browser outside the cluster network. |

---

## Notes

- Issue `#7` (cart) was on the original scope list but was dropped — the platform exercise was already complete, and the layout already reserves a slot for a cart button to land later.
- `CLAUDE.md` and `docs/agents/` document conventions for AI-assisted development on this repo — issue-tracker workflow, triage labels, and the single-context domain layout. This project was built with [Claude Code](https://claude.com/claude-code) pair-driving.
