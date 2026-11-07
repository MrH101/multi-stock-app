# Architecture & domain rules

## Services

| Service | Owns | Key rules |
|---|---|---|
| **identity** | Organisations (PHARMACY / SUPPLIER / PLATFORM), users, roles (OWNER / MANAGER / STAFF) | Registering creates an org + owner. Only owners manage the team. Platform admins verify licences and suspend orgs. |
| **catalog** | Products, batches (batch no. + expiry), reservations, stock movement ledger | Expired batches are never sellable. Reservations allocate **FEFO** (first-expiry-first-out) and are all-or-nothing, with row locks on Postgres. Every stock change is written to an append-only ledger. |
| **orders** | Purchase orders, lines (with allocated batches), status history, monthly budgets | One cart → **one PO per supplier**. If any supplier's reservation fails, earlier ones are released (compensation). Checkout is idempotent per cart key. |
| **notifications** | Notifications (per-user read state), conversations, broadcasts, WebSocket | Consumes order and agent events. Suppliers broadcast only to pharmacies. |
| **agent** | Alerts, briefings (digests), monitor runs | Reads other services only through `/internal/monitoring/*` snapshots (service token). Publishes `agent.alert` events, and notifications delivers them. |

## Order workflow

```
SUBMITTED ──supplier──► ACCEPTED ──supplier──► DISPATCHED ──either──► DELIVERED
    │  └─supplier─► REJECTED (reason required)        (stock committed)
    └──pharmacy/supplier──► CANCELLED (from SUBMITTED or ACCEPTED)
REJECTED / CANCELLED release reserved stock back to the batches.
```

## Monitoring agent

Every `MONITOR_INTERVAL_SECONDS` (default 15 min) one replica runs the following steps. A database lease makes sure only one replica does this.

1. **Collect** snapshots: catalog (stock, 30-day demand, expiring batches), orders (budgets, open orders, what each pharmacy buys), identity (organisations) and `/health` of every service.
2. **Detect** with deterministic rules (`services/agent/app/rules.py`). The model never decides what counts as a problem.

   | Who | Rule | Severity |
   |---|---|---|
   | Supplier | Out of stock (with demand or a reorder level) | urgent |
   | Supplier | Days of cover < 7 / < 14 at current demand, or at/below reorder level, with a suggested replenishment quantity | urgent / review |
   | Supplier | Expired batch still on hand · expiring ≤ 30 / ≤ 90 days, with units that won't sell in time | urgent / urgent / review |
   | Supplier | Order not reviewed within 24 h (urgent after 48 h) · accepted but not dispatched within 48 h | review |
   | Pharmacy | Budget ≥ 100 % · ≥ 80 % · projected to overrun (from day 5) · ≥ 50 % | urgent / review / review / FYI |
   | Pharmacy | Regularly ordered item out of stock or scarce at its supplier, with in-stock alternatives (same generic + strength) | review / FYI |
   | Pharmacy | Dispatched order not confirmed delivered within 72 h · order still waiting for the supplier | review / FYI |
   | Platform | Service down · a data source unreadable · AI calls failing | urgent / review / review |

3. **Reconcile.** There is one live alert per `(organisation, key)`, so repeated runs update it instead of duplicating it. An alert resolves by itself when its condition clears. If a source could not be read, its alerts are left untouched rather than wrongly resolved. An acknowledged alert reopens if it gets worse.
4. **Notify** on new or escalated urgent/review alerts only, never FYI, with at most 5 notifications per organisation per run (the rest are summarised). Delivery goes through the notifications service: in-app, plus WebSocket toast.
5. **Brief.** When an organisation's alert set changes, Caimex (`CAIMEX_MODEL`, with fallbacks) writes a headline, a summary and up to 5 actions as JSON. Actions must reference real alert ids, and anything else is dropped. Links always come from the alert, never from the model. If the model fails, a rule-based briefing is used.

**Assistant** (`POST /assistant`): a read-only tool-calling loop. Each tool calls the owning service's *public* API with the user's own JWT, so it can only see what that user can see in the app. It refuses clinical and dosing advice, treats tool output as data, and is rate-limited per user.

**Operations:** platform admins get `/monitoring` (service health, runs, AI usage and cost, alerts across orgs, "Run checks now"). The agent exposes Prometheus metrics at `agent:8000/metrics` (blocked at the gateway). `POST /internal/run` lets an external scheduler drive it when `MONITOR_ENABLED=false`.

**Data sent to Caimex:** business data only, such as product names, quantities, prices, budget totals, order numbers and organisation names. No patient data exists in the system. Review the Caimex workspace's data policy (zero data retention, region) before going live.

## Frontend

The SPA is split into domain modules that mirror the services (`src/modules/<domain>/api.ts` + pages). Each module is lazy-loaded. The `shared/` folder holds the HTTP client (silent token refresh, readable error messages), the session store, the realtime hook and UI primitives.

Usability choices for pharmacy staff: one search box over all suppliers (`/` focuses it), quantity + Add on every row, colour-coded expiry and stock badges, plain-language order statuses, confirmations before irreversible steps, a budget warning that doesn't block ordering, and printable POs.

## Before going live (not done yet)

- [ ] Alembic migrations per service. Services currently use `create_all`, which won't alter existing tables.
- [ ] Switch JWT from a shared HS256 secret to RS256 with a JWKS endpoint on identity.
- [ ] Put the refresh token in an httpOnly cookie instead of localStorage.
- [ ] Redis pub/sub fan-out so the notifications service can run more than one replica (WebSocket connections are per process).
- [ ] Transactional outbox for events. Today an event can be lost if Redis is down right after a commit.
- [ ] Email/WhatsApp delivery for notifications, and password reset.
- [ ] Data migration from `legacy/db.sqlite3`, tracing (OpenTelemetry), a Prometheus/Grafana stack for the agent's `/metrics`, CI pipeline.
- [ ] Role-targeted alerts (e.g. budget alerts only to owners/managers) and email/WhatsApp delivery for urgent ones. Alerts are currently org-wide in-app notifications.
- [ ] Monitoring snapshots return every active product in one call. Paginate them once catalogs reach tens of thousands of items.
- [ ] Use a dedicated, budget-capped Caimex key per environment, and rotate the key used during development.
- [ ] Frontend unit/e2e tests (Vitest + Playwright).
