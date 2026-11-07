# Multi-Stock

A B2B platform where **pharmacies** order medicines from licensed **suppliers/wholesalers**, with batch and expiry tracking, purchase-order workflows, budgets and messaging. Built for Zimbabwe (MCAZ licences, USD/ZWG) but not tied to it.

> The original Django monolith is kept in [`legacy/`](legacy/) for reference only.

## Architecture

```
                    ┌──────────── React SPA (frontend/) ───────────┐
                    │ modules: identity · catalog · orders · messaging · insights · dashboard │
                    └──────────────────────┬───────────────────────┘
                                           │  /api/<service>/...
                                 ┌─────────▼─────────┐
                                 │ API gateway (nginx)│  TLS, rate-limit on /auth, blocks /internal
                                 └─┬──────┬──────┬───┬┘
              ┌────────────────────┘      │      │   └──────────────────┐
     ┌────────▼───────┐  ┌────────────────▼┐  ┌──▼───────────┐  ┌───────▼────────────┐
     │ identity        │  │ catalog          │  │ orders        │  │ notifications       │
     │ orgs, users,    │  │ products, batches│◄─┤ checkout, PO  │  │ in-app alerts, WS,  │
     │ JWT, team, admin│  │ FEFO reservations│  │ workflow,     │  │ messaging,          │
     │                 │  │ stock ledger     │  │ budgets, KPIs │  │ broadcasts          │
     └───────┬─────────┘  └───────┬──────────┘  └──────┬────────┘  └────────▲───────────┘
             │ Postgres db         │ Postgres db         │ Postgres db         │ Postgres db
             └──────────── events ─┴──── Redis Streams ──┴─────────────────────┘
```

* **Database per service** — no service reads another's tables.
* **Auth**: identity issues short-lived JWT access tokens (+ refresh tokens); every other service verifies them locally.
* **Sync calls** only where consistency is needed: orders → catalog `/internal/reservations` (service token, idempotent, retried).
* **Async events** (`order.created`, `order.status_changed`, …) on Redis Streams with consumer groups; notifications turns them into alerts and pushes over WebSocket.
* **Monitoring agent** (`services/agent`, :8005) checks every organisation's stock, expiry dates, orders and budgets on a schedule. It raises de-duplicated alerts, notifies the right organisation, writes a daily-style briefing and answers questions. AI text comes from [Caimex](https://api.caimex.ai) (OpenAI-compatible); the rules work without it.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the domain rules and the production checklist.

## Run it

**Docker (production-like):**
```bash
cp .env.example .env     # change the secrets; set CAIMEX_API_KEY to turn on AI briefings + assistant
docker compose up --build
# http://localhost:8080   admin: admin@multistock.app / value of ADMIN_PASSWORD
```

**Without Docker** (needs `uv` and Node 20+; uses SQLite and HTTP instead of Redis):
```bash
./scripts/dev.sh         # http://localhost:5173
```
Service API docs: `http://localhost:800{1..6}/docs` (identity, catalog, orders, notifications, agent, payments). `scripts/dev.sh` loads secrets such as `CAIMEX_API_KEY` from the git-ignored `.env` at the repo root.

**Tests:** `cd services/<name> && uv run pytest`

## Repository layout
```
libs/common/            shared Python package: auth, db, events, app factory
services/identity/      :8001
services/catalog/       :8002
services/orders/        :8003
services/notifications/ :8004
services/agent/         :8005  monitoring agent: rules, alerts, AI briefings, assistant, /metrics
services/payments/      :8006  Paynow (EcoCash, OneMoney, InnBucks, cards) and proof-of-payment
frontend/               React + TypeScript + Vite + Mantine + TanStack Query
gateway/nginx.conf      API gateway
infra/                  Postgres init (one database per service)
legacy/                 original Django app (reference only)
```
