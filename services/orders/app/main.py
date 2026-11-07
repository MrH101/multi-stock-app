import secrets
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Annotated

from fastapi import Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from multistock_common.app import create_app
from multistock_common.auth import CurrentUser, OrgType, Principal, Role, require_org, require_service
from multistock_common.db import Database
from multistock_common.events import EventPublisher

from . import fx, schemas, workflow
from .catalog_client import CatalogClient, get_catalog
from .config import settings
from .models import Budget, Order, OrderEvent, OrderLine, OrderStatus

db = Database(settings.database_url)
events = EventPublisher(settings.redis_url, settings.event_stream, "orders",
                        settings.event_webhook_url, settings.service_token)


@asynccontextmanager
async def lifespan(_app):
    db.create_all()
    db.ensure_columns("order_lines", {"schedule": "VARCHAR(20)", "mcaz_registration_number": "VARCHAR(60)"})
    db.ensure_columns("orders", {"fx_rates": "JSON", "amount_usd": "NUMERIC(14, 2)", "payment_status": "VARCHAR(30)",
                                 "paid_at": "TIMESTAMP", "paid_via": "VARCHAR(30)"})
    yield


app = create_app(settings, "Orders Service")
app.router.lifespan_context = lifespan
DB = Annotated[Session, Depends(db.session)]
Catalog = Annotated[CatalogClient, Depends(get_catalog)]
Pharmacy = Annotated[Principal, require_org(OrgType.PHARMACY)]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _month_start(d: date | None = None) -> date:
    d = d or date.today()
    return d.replace(day=1)


def _scope(stmt, p: Principal):
    if p.is_pharmacy:
        return stmt.where(Order.pharmacy_org_id == p.org_id)
    if p.is_supplier:
        return stmt.where(Order.supplier_org_id == p.org_id)
    return stmt  # platform admin sees everything


def _summary(o: Order) -> dict:
    data = schemas.OrderSummaryOut.model_validate(o).model_dump()
    data["item_count"] = sum(l.quantity for l in o.lines)
    return data


def _detail(o: Order, p: Principal) -> dict:
    data = schemas.OrderOut.model_validate({**_summary(o), **{
        k: getattr(o, k) for k in ("payment_method", "delivery_address", "contact_name",
                                   "contact_phone", "notes", "lines", "history")}}).model_dump()
    data["allowed_transitions"] = workflow.allowed(o.status, p.org_type)
    return data


def _event_payload(o: Order) -> dict:
    return {"order_id": o.id, "order_number": o.order_number, "status": o.status,
            "pharmacy_org_id": o.pharmacy_org_id, "pharmacy_name": o.pharmacy_name,
            "supplier_org_id": o.supplier_org_id, "supplier_name": o.supplier_name,
            "subtotal": str(o.subtotal), "currency": o.currency}


# ---------------------------------------------------------------- checkout
@app.post("/orders/checkout", response_model=list[schemas.OrderOut], status_code=201, tags=["orders"])
def checkout(body: schemas.CheckoutRequest, p: Pharmacy, s: DB, catalog: Catalog):
    """Turn a cart into one purchase order per supplier, reserving stock for each."""
    checkout_ref = body.idempotency_key or secrets.token_hex(8)
    if body.idempotency_key:
        existing = s.scalars(select(Order).where(Order.checkout_ref == checkout_ref,
                                                 Order.pharmacy_org_id == p.org_id)).all()
        if existing:
            return [_detail(o, p) for o in existing]

    quantities: dict[int, int] = defaultdict(int)
    for line in body.lines:
        quantities[line.product_id] += line.quantity
    products = {x["id"]: x for x in catalog.products(list(quantities))}
    missing = [pid for pid in quantities if pid not in products or not products[pid]["is_active"]]
    if missing:
        raise HTTPException(409, {"message": "Some items are no longer available", "product_ids": missing})

    # One PO per supplier and currency: a PO's lines must share a currency for its total to mean anything.
    by_supplier: dict[tuple[int, str], list[dict]] = defaultdict(list)
    for pid, qty in quantities.items():
        key = (products[pid]["supplier_org_id"], products[pid]["currency"])
        by_supplier[key].append({"product_id": pid, "quantity": qty})
    rates = fx.current_rates(s)

    reserved_refs: list[str] = []
    orders: list[Order] = []
    try:
        for (supplier_id, _currency), lines in by_supplier.items():
            order_number = f"PO-{date.today():%y%m%d}-{secrets.token_hex(3).upper()}"
            reserved = catalog.reserve(order_number, lines)
            reserved_refs.append(order_number)
            order = Order(
                order_number=order_number, checkout_ref=checkout_ref,
                pharmacy_org_id=p.org_id, pharmacy_name=p.org_name,
                supplier_org_id=supplier_id, supplier_name=reserved[0]["supplier_name"],
                created_by_user_id=p.user_id, created_by_name=p.name,
                payment_method=body.payment_method, delivery_address=body.delivery_address,
                contact_name=body.contact_name, contact_phone=body.contact_phone, notes=body.notes,
                currency=reserved[0]["currency"], subtotal=Decimal("0"),
            )
            for r in reserved:
                price = Decimal(str(r["unit_price"]))
                order.lines.append(OrderLine(
                    product_id=r["product_id"], product_name=r["product_name"], generic_name=r["generic_name"],
                    strength=r["strength"], pack_size=r["pack_size"], quantity=r["quantity"],
                    unit_price=price, line_total=price * r["quantity"], allocations=r["allocations"],
                    schedule=r.get("schedule"), mcaz_registration_number=r.get("mcaz_registration_number")))
            order.subtotal = sum((l.line_total for l in order.lines), Decimal("0"))
            order.fx_rates = fx.snapshot(rates)
            order.amount_usd = fx.convert(order.subtotal, order.currency, fx.BASE, rates)
            order.history.append(OrderEvent(status=OrderStatus.SUBMITTED, note=body.notes, actor_name=p.name,
                                            actor_org_name=p.org_name, at=_now()))
            s.add(order)
            orders.append(order)
        s.commit()
    except Exception:
        s.rollback()
        for ref in reserved_refs:  # compensate: give the stock back
            try:
                catalog.release(ref)
            except Exception:
                pass
        raise

    for o in orders:
        events.publish("order.created", _event_payload(o))
    return [_detail(o, p) for o in orders]


# ---------------------------------------------------------------- read
@app.get("/orders", response_model=schemas.OrderPage, tags=["orders"])
def list_orders(p: CurrentUser, s: DB, status: list[OrderStatus] = Query(default=[]),
                q: str | None = None, page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100)):
    stmt = _scope(select(Order), p)
    if status:
        stmt = stmt.where(Order.status.in_(status))
    if q:
        term = f"%{q.lower()}%"
        stmt = stmt.where(or_(func.lower(Order.order_number).like(term), func.lower(Order.pharmacy_name).like(term),
                              func.lower(Order.supplier_name).like(term)))
    total = s.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = s.scalars(stmt.options(selectinload(Order.lines)).order_by(Order.created_at.desc())
                     .offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": [_summary(o) for o in rows], "total": total, "page": page, "page_size": page_size}


@app.get("/orders/summary", response_model=schemas.DashboardSummary, tags=["reports"])
def dashboard_summary(p: CurrentUser, s: DB, currency: str = Query("USD", pattern="^(USD|ZWG|ZAR)$")):
    counts = dict(s.execute(_scope(select(Order.status, func.count()), p).group_by(Order.status)).all())
    counts = {st: counts.get(st, 0) for st in OrderStatus}
    open_orders = sum(counts[st] for st in workflow.OPEN)

    months_back = date.today().year * 12 + date.today().month - 1 - 5  # this month + previous 5
    since = date(months_back // 12, months_back % 12 + 1, 1)
    rows = s.scalars(_scope(select(Order), p).options(selectinload(Order.lines))
                     .where(Order.created_at >= datetime.combine(since, datetime.min.time(), timezone.utc),
                            Order.status.in_(workflow.COMMITTED_SPEND))).all()
    monthly: dict[str, Decimal] = {}
    cursor = since
    while cursor <= date.today():
        monthly[f"{cursor:%Y-%m}"] = Decimal("0")
        cursor = date(cursor.year + cursor.month // 12, cursor.month % 12 + 1, 1)
    today_rates = fx.current_rates(s)
    top: dict[int, dict] = {}
    unconverted: set[str] = set()
    for o in rows:
        rates = {**today_rates, **fx.parse(o.fx_rates)} if o.fx_rates else today_rates
        value = fx.convert(o.subtotal, o.currency, currency, rates)
        if value is None:
            unconverted.add(o.currency)
            continue
        key = f"{o.created_at:%Y-%m}"
        if key in monthly:
            monthly[key] += value
        for l in o.lines:
            t_ = top.setdefault(l.product_id, {"product_id": l.product_id, "product_name": l.product_name,
                                               "quantity": 0, "total": Decimal("0")})
            t_["quantity"] += l.quantity
            t_["total"] += fx.convert(l.line_total, o.currency, currency, rates)
    return {
        "counts": counts, "open_orders": open_orders, "currency": currency,
        "month_total": monthly.get(f"{date.today():%Y-%m}", Decimal("0")),
        "monthly": [{"month": m, "total": v} for m, v in monthly.items()],
        "top_products": sorted(top.values(), key=lambda x: x["total"], reverse=True)[:5],
        "unconverted_currencies": sorted(unconverted),
    }


def _get_order(s: Session, order_id: int, p: Principal, lock: bool = False) -> Order:
    stmt = _scope(select(Order).where(Order.id == order_id), p)
    if lock:
        stmt = stmt.with_for_update()
    order = s.scalar(stmt)
    if not order:
        raise HTTPException(404, "Order not found")
    return order


@app.get("/orders/{order_id}", response_model=schemas.OrderOut, tags=["orders"])
def get_order(order_id: int, p: CurrentUser, s: DB):
    return _detail(_get_order(s, order_id, p), p)


# ---------------------------------------------------------------- workflow
@app.post("/orders/{order_id}/status", response_model=schemas.OrderOut, tags=["orders"])
def change_status(order_id: int, body: schemas.StatusChange, p: CurrentUser, s: DB, catalog: Catalog):
    order = _get_order(s, order_id, p, lock=True)
    if body.status not in workflow.allowed(order.status, p.org_type):
        raise HTTPException(409, f"An order that is {order.status.lower()} cannot be marked {body.status.lower()}")
    if body.status == OrderStatus.REJECTED and not body.note:
        raise HTTPException(400, "Please give the pharmacy a reason for rejecting the order")

    if body.status in workflow.RELEASES_STOCK:
        catalog.release(order.order_number)
    elif body.status in workflow.COMMITS_STOCK:
        catalog.commit(order.order_number)

    previous = order.status
    order.status = body.status
    order.history.append(OrderEvent(status=body.status, note=body.note, actor_name=p.name,
                                    actor_org_name=p.org_name, at=_now()))
    s.commit()
    events.publish("order.status_changed", {**_event_payload(order), "previous_status": previous,
                                            "note": body.note, "changed_by_org_type": p.org_type})
    return _detail(order, p)


# ---------------------------------------------------------------- budgets
def _budget_out(s: Session, org_id: int) -> dict:
    """This month's budget with committed spend from orders in *any* currency, converted at each order's
    checkout rate (orders from before rates were recorded use today's rate)."""
    period = _month_start()
    budget = s.scalar(select(Budget).where(Budget.pharmacy_org_id == org_id, Budget.period == period))
    currency = budget.currency if budget else "USD"
    orders = s.execute(select(Order.subtotal, Order.currency, Order.fx_rates).where(
        Order.pharmacy_org_id == org_id, Order.status.in_(workflow.COMMITTED_SPEND),
        Order.created_at >= datetime.combine(period, datetime.min.time(), timezone.utc))).all()
    today_rates = fx.current_rates(s)
    committed, unconverted = Decimal("0.00"), set()
    for subtotal, cur, snap in orders:
        rates = {**today_rates, **fx.parse(snap)} if snap else today_rates
        value = fx.convert(subtotal, cur, currency, rates)
        if value is None:
            unconverted.add(cur)
        else:
            committed += value
    amount = budget.amount if budget else Decimal("0")
    return {"period": period, "amount": amount, "currency": currency, "committed": committed,
            "remaining": amount - committed, "is_set": budget is not None,
            "percent_used": float(committed / amount * 100) if amount else 0.0,
            "unconverted_currencies": sorted(unconverted)}


@app.get("/budget", response_model=schemas.BudgetOut, tags=["budget"])
def get_budget(p: Pharmacy, s: DB):
    return _budget_out(s, p.org_id)


@app.put("/budget", response_model=schemas.BudgetOut, tags=["budget"])
def set_budget(body: schemas.BudgetIn, s: DB, p: Principal = require_org(OrgType.PHARMACY)):
    if p.role == Role.STAFF:
        raise HTTPException(403, "Only owners and managers can set the budget")
    period = _month_start()
    budget = s.scalar(select(Budget).where(Budget.pharmacy_org_id == p.org_id, Budget.period == period))
    if not budget:
        budget = Budget(pharmacy_org_id=p.org_id, period=period)
        s.add(budget)
    budget.amount, budget.currency = body.amount, body.currency.upper()
    s.commit()
    return _budget_out(s, p.org_id)


# ---------------------------------------------------------------- exchange rates
@app.get("/fx/rates", response_model=schemas.RatesOut, tags=["exchange rates"])
def get_rates(_p: CurrentUser, s: DB):
    return fx.info(s)


@app.put("/admin/fx/rates", response_model=schemas.RatesOut, tags=["exchange rates"])
def set_rates(body: schemas.RatesIn, s: DB, p: Principal = require_org(OrgType.PLATFORM)):
    effective = body.effective_date or date.today()
    if effective > date.today():
        raise HTTPException(400, "The effective date cannot be in the future")
    for currency, per_usd in body.rates.items():
        s.add(fx.ExchangeRate(currency=currency, per_usd=per_usd, effective_date=effective, source=body.source,
                              set_by=p.name, set_by_user_id=p.user_id))
    s.commit()
    out = fx.info(s)
    events.publish("fx.rates_updated", {"rates": out["rates"], "effective_date": effective.isoformat()})
    return out


@app.get("/admin/fx/history", response_model=list[schemas.RateHistoryOut], tags=["exchange rates"])
def rate_history(s: DB, _p: Principal = require_org(OrgType.PLATFORM), limit: int = Query(60, ge=1, le=500)):
    return s.scalars(select(fx.ExchangeRate).order_by(fx.ExchangeRate.id.desc()).limit(limit)).all()


# ---------------------------------------------------------------- internal (payments service)
def _by_number(s: Session, order_number: str) -> Order:
    order = s.scalar(select(Order).where(Order.order_number == order_number))
    if not order:
        raise HTTPException(404, "Order not found")
    return order


@app.get("/internal/orders/{order_number}", response_model=schemas.InternalOrder, tags=["internal"],
         dependencies=[Depends(require_service)])
def internal_order(order_number: str, s: DB):
    return _by_number(s, order_number)


@app.post("/internal/orders/{order_number}/payment", response_model=schemas.InternalOrder, tags=["internal"],
          dependencies=[Depends(require_service)])
def record_payment(order_number: str, body: schemas.PaymentUpdate, s: DB):
    """Called by the payments service when a payment's state changes. Idempotent."""
    order = _by_number(s, order_number)
    order.payment_status = body.payment_status
    if body.paid_via:
        order.paid_via = body.paid_via
    if body.payment_status == "PAID":
        order.paid_at = order.paid_at or body.paid_at or _now()
    s.commit()
    return order


# ---------------------------------------------------------------- internal (monitoring agent)
@app.get("/internal/monitoring/snapshot", tags=["internal"], dependencies=[Depends(require_service)])
def monitoring_snapshot(s: DB, demand_days: int = Query(90, ge=7, le=365)):
    """Everything the monitoring agent needs from this service in one call: this month's budgets with
    committed spend, open orders with how long they have sat in their current status, and what each
    pharmacy has been ordering (so it can watch supply of the items they depend on)."""
    import calendar

    today = date.today()
    period = _month_start()
    budgets = []
    for b in s.scalars(select(Budget).where(Budget.period == period)):
        out = {k: str(v) if isinstance(v, Decimal) else v for k, v in _budget_out(s, b.pharmacy_org_id).items()}
        budgets.append({**out, "pharmacy_org_id": b.pharmacy_org_id, "days_elapsed": today.day,
                        "days_in_month": calendar.monthrange(today.year, today.month)[1]})

    last_change = (select(OrderEvent.order_id, func.max(OrderEvent.at).label("at"))
                   .group_by(OrderEvent.order_id).subquery())
    open_rows = s.execute(select(Order, last_change.c.at).outerjoin(last_change, last_change.c.order_id == Order.id)
                          .where(Order.status.in_(workflow.OPEN))).all()
    open_orders = [{
        "id": o.id, "order_number": o.order_number, "status": o.status,
        "pharmacy_org_id": o.pharmacy_org_id, "pharmacy_name": o.pharmacy_name,
        "supplier_org_id": o.supplier_org_id, "supplier_name": o.supplier_name,
        "subtotal": str(o.subtotal), "currency": o.currency, "created_at": o.created_at,
        "status_since": at or o.created_at,
    } for o, at in open_rows]

    since = datetime.combine(today, datetime.min.time(), timezone.utc) - timedelta(days=demand_days)
    demand_rows = s.execute(
        select(Order.pharmacy_org_id, Order.supplier_org_id, OrderLine.product_id, OrderLine.product_name,
               func.sum(OrderLine.quantity), func.count(func.distinct(Order.id)))
        .join(OrderLine, OrderLine.order_id == Order.id)
        .where(Order.created_at >= since, Order.status.in_(workflow.COMMITTED_SPEND))
        .group_by(Order.pharmacy_org_id, Order.supplier_org_id, OrderLine.product_id, OrderLine.product_name)).all()
    demand = [{"pharmacy_org_id": ph, "supplier_org_id": sup, "product_id": pid, "product_name": name,
               "quantity": int(qty), "order_count": int(n)} for ph, sup, pid, name, qty, n in demand_rows]
    return {"as_of": today, "budgets": budgets, "open_orders": open_orders, "demand": demand,
            "demand_days": demand_days, "fx": fx.info(s)}
