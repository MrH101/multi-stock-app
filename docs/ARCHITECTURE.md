# Architecture & domain rules

## Services

| Service | Owns | Key rules |
|---|---|---|
| **identity** | Organisations (PHARMACY / SUPPLIER / PLATFORM), users, roles (OWNER / MANAGER / STAFF) | Registering creates an org + owner. Only owners manage the team. Platform admins verify licences and suspend orgs. |
| **catalog** | Products, batches (batch no. + expiry), reservations, stock movement ledger | Expired batches are never sellable. Reservations allocate **FEFO** (first-expiry-first-out) and are all-or-nothing, with row locks on Postgres. Every stock change is written to an append-only ledger. |
| **orders** | Purchase orders, lines (with allocated batches), status history, monthly budgets | One cart → **one PO per supplier**. If any supplier's reservation fails, earlier ones are released (compensation). Checkout is idempotent per cart key. |
| **notifications** | Notifications (per-user read state), conversations, broadcasts, WebSocket | Consumes order events. Suppliers broadcast only to pharmacies. |

## Order workflow

```
SUBMITTED ──supplier──► ACCEPTED ──supplier──► DISPATCHED ──either──► DELIVERED
    │  └─supplier─► REJECTED (reason required)        (stock committed)
    └──pharmacy/supplier──► CANCELLED (from SUBMITTED or ACCEPTED)
REJECTED / CANCELLED release reserved stock back to the batches.
```

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
- [ ] Scheduled expiry alerts, data migration from `legacy/db.sqlite3`, observability (OpenTelemetry, metrics), CI pipeline.
- [ ] Frontend unit/e2e tests (Vitest + Playwright).
