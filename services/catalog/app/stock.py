"""Stock rules: FEFO allocation, reservation lifecycle and the movement ledger."""
from collections import defaultdict
from datetime import date

from fastapi import HTTPException
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from .models import Batch, MovementReason, Product, Reservation, ReservationStatus, StockMovement


def record(s: Session, batch: Batch, change: int, reason: MovementReason,
           reference: str | None = None, note: str | None = None, user_id: int | None = None) -> None:
    s.add(StockMovement(batch_id=batch.id, change=change, reason=reason,
                        reference=reference, note=note, user_id=user_id))


def stock_summary(s: Session, product_ids: list[int]) -> dict[int, tuple[int, date | None]]:
    """Sellable stock (non-expired) and the nearest expiry per product."""
    if not product_ids:
        return {}
    today = date.today()
    rows = s.execute(
        select(
            Batch.product_id,
            func.coalesce(func.sum(Batch.quantity_available), 0),
            func.min(case((Batch.quantity_available > 0, Batch.expiry_date))),
        )
        .where(Batch.product_id.in_(product_ids), Batch.expiry_date > today)
        .group_by(Batch.product_id)
    ).all()
    return {pid: (int(qty), nearest) for pid, qty, nearest in rows}


def reserve(s: Session, order_ref: str, lines: list[tuple[int, int]]) -> list[dict]:
    """All-or-nothing reservation, allocating from the earliest-expiring batches first (FEFO)."""
    existing = s.scalars(select(Reservation).where(
        Reservation.order_ref == order_ref, Reservation.status == ReservationStatus.RESERVED)).all()
    if existing:  # idempotent retry from the orders service
        return _describe(s, existing)

    wanted: dict[int, int] = defaultdict(int)
    for product_id, qty in lines:
        wanted[product_id] += qty

    products = {p.id: p for p in s.scalars(select(Product).where(Product.id.in_(wanted)))}
    problems = []
    plan: list[tuple[Batch, int]] = []
    for product_id, qty in wanted.items():
        product = products.get(product_id)
        if not product or not product.is_active:
            problems.append(f"Product {product_id} is no longer available")
            continue
        batches = s.scalars(
            select(Batch)
            .where(Batch.product_id == product_id, Batch.expiry_date > date.today(), Batch.quantity_available > 0)
            .order_by(Batch.expiry_date, Batch.id)
            .with_for_update()  # row locks on Postgres prevent overselling under concurrency
        ).all()
        remaining = qty
        for batch in batches:
            take = min(batch.quantity_available, remaining)
            plan.append((batch, take))
            remaining -= take
            if remaining == 0:
                break
        if remaining:
            available = qty - remaining
            problems.append(f"{product.name}: only {available} in stock, {qty} requested")
    if problems:
        s.rollback()
        raise HTTPException(409, {"message": "Some items cannot be fulfilled", "problems": problems})

    reservations = []
    for batch, take in plan:
        batch.quantity_available -= take
        batch.quantity_reserved += take
        record(s, batch, -take, MovementReason.RESERVED, reference=order_ref)
        r = Reservation(order_ref=order_ref, batch_id=batch.id, product_id=batch.product_id, quantity=take)
        r.batch = batch
        s.add(r)
        reservations.append(r)
    s.commit()
    return _describe(s, reservations)


def release(s: Session, order_ref: str) -> int:
    count = 0
    for r in s.scalars(select(Reservation).where(
            Reservation.order_ref == order_ref, Reservation.status == ReservationStatus.RESERVED)):
        r.batch.quantity_reserved -= r.quantity
        r.batch.quantity_available += r.quantity
        r.status = ReservationStatus.RELEASED
        record(s, r.batch, r.quantity, MovementReason.RELEASED, reference=order_ref)
        count += 1
    s.commit()
    return count


def commit(s: Session, order_ref: str) -> int:
    count = 0
    for r in s.scalars(select(Reservation).where(
            Reservation.order_ref == order_ref, Reservation.status == ReservationStatus.RESERVED)):
        r.batch.quantity_reserved -= r.quantity
        r.status = ReservationStatus.COMMITTED
        record(s, r.batch, 0, MovementReason.DISPATCHED, reference=order_ref, note=f"{r.quantity} units shipped")
        count += 1
    s.commit()
    return count


def _describe(s: Session, reservations: list[Reservation]) -> list[dict]:
    by_product: dict[int, dict] = {}
    for r in reservations:
        p = r.batch.product
        line = by_product.setdefault(p.id, {
            "product_id": p.id, "product_name": p.name, "generic_name": p.generic_name,
            "strength": p.strength, "pack_size": p.pack_size, "supplier_org_id": p.supplier_org_id,
            "supplier_name": p.supplier_name, "unit_price": p.unit_price, "currency": p.currency,
            "quantity": 0, "allocations": [],
        })
        line["quantity"] += r.quantity
        line["allocations"].append({"batch_number": r.batch.batch_number,
                                    "expiry_date": r.batch.expiry_date, "quantity": r.quantity})
    return list(by_product.values())
