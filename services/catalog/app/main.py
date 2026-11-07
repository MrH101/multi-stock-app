from contextlib import asynccontextmanager
from datetime import date, timedelta
from typing import Annotated

from fastapi import Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from multistock_common.app import create_app
from multistock_common.auth import CurrentUser, OrgType, Principal, require_org, require_service
from multistock_common.db import Database
from multistock_common.events import EventPublisher

from . import schemas, stock
from .config import settings
from .models import Batch, DosageForm, MovementReason, Product, StockMovement

db = Database(settings.database_url)
events = EventPublisher(settings.redis_url, settings.event_stream, "catalog",
                        settings.event_webhook_url, settings.service_token)


@asynccontextmanager
async def lifespan(_app):
    db.create_all()
    yield


app = create_app(settings, "Catalog & Inventory Service")
app.router.lifespan_context = lifespan
DB = Annotated[Session, Depends(db.session)]
Supplier = Annotated[Principal, require_org(OrgType.SUPPLIER)]


def _with_stock(s: Session, products: list[Product]) -> list[dict]:
    summary = stock.stock_summary(s, [p.id for p in products])
    out = []
    for p in products:
        qty, nearest = summary.get(p.id, (0, None))
        out.append({**schemas.ProductOut.model_validate(p, from_attributes=True).model_dump(),
                    "stock_available": qty, "nearest_expiry": nearest})
    return out


def _own_product(s: Session, product_id: int, p: Principal) -> Product:
    product = s.get(Product, product_id)
    if not product or product.supplier_org_id != p.org_id:
        raise HTTPException(404, "Product not found")
    return product


# ---------------------------------------------------------------- browsing (all signed-in users)
@app.get("/products", response_model=schemas.ProductPage, tags=["catalog"])
def search_products(
    _p: CurrentUser, s: DB,
    q: str | None = Query(None, description="Search brand name, generic name or manufacturer"),
    dosage_form: DosageForm | None = None,
    supplier_org_id: int | None = None,
    in_stock: bool = False,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
):
    stmt = select(Product).where(Product.is_active.is_(True))
    if q:
        term = f"%{q.lower()}%"
        stmt = stmt.where(or_(func.lower(Product.name).like(term), func.lower(Product.generic_name).like(term),
                              func.lower(Product.manufacturer).like(term), func.lower(Product.sku).like(term)))
    if dosage_form:
        stmt = stmt.where(Product.dosage_form == dosage_form)
    if supplier_org_id:
        stmt = stmt.where(Product.supplier_org_id == supplier_org_id)
    if in_stock:
        sellable = (select(Batch.product_id)
                    .where(Batch.quantity_available > 0, Batch.expiry_date > date.today()))
        stmt = stmt.where(Product.id.in_(sellable))
    total = s.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = s.scalars(stmt.order_by(Product.name, Product.unit_price)
                     .offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": _with_stock(s, rows), "total": total, "page": page, "page_size": page_size}


@app.get("/products/{product_id}", response_model=schemas.ProductDetail, tags=["catalog"])
def get_product(product_id: int, p: CurrentUser, s: DB):
    product = s.get(Product, product_id)
    if not product or (not product.is_active and product.supplier_org_id != p.org_id):
        raise HTTPException(404, "Product not found")
    data = _with_stock(s, [product])[0]
    data["batches"] = [b for b in product.batches if b.quantity_available > 0 and b.expiry_date > date.today()]
    return data


# ---------------------------------------------------------------- supplier: product management
@app.get("/supplier/products", response_model=schemas.ProductPage, tags=["supplier"])
def my_products(p: Supplier, s: DB, q: str | None = None, include_inactive: bool = True,
                page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200)):
    stmt = select(Product).where(Product.supplier_org_id == p.org_id)
    if not include_inactive:
        stmt = stmt.where(Product.is_active.is_(True))
    if q:
        term = f"%{q.lower()}%"
        stmt = stmt.where(or_(func.lower(Product.name).like(term), func.lower(Product.generic_name).like(term),
                              func.lower(Product.sku).like(term)))
    total = s.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = s.scalars(stmt.order_by(Product.name).offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": _with_stock(s, rows), "total": total, "page": page, "page_size": page_size}


@app.post("/products", response_model=schemas.ProductOut, status_code=201, tags=["supplier"])
def create_product(body: schemas.ProductCreate, p: Supplier, s: DB):
    product = Product(**body.model_dump(), supplier_org_id=p.org_id, supplier_name=p.org_name)
    s.add(product)
    try:
        s.commit()
    except IntegrityError:
        raise HTTPException(409, "A product with this SKU already exists")
    events.publish("product.created", {"product_id": product.id, "supplier_org_id": p.org_id})
    return _with_stock(s, [product])[0]


@app.patch("/products/{product_id}", response_model=schemas.ProductOut, tags=["supplier"])
def update_product(product_id: int, body: schemas.ProductUpdate, p: Supplier, s: DB):
    product = _own_product(s, product_id, p)
    changes = body.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(product, k, v)
    try:
        s.commit()
    except IntegrityError:
        raise HTTPException(409, "A product with this SKU already exists")
    if "unit_price" in changes:
        events.publish("product.price_changed", {"product_id": product.id, "unit_price": str(product.unit_price)})
    return _with_stock(s, [product])[0]


# ---------------------------------------------------------------- supplier: batches & stock
@app.get("/products/{product_id}/batches", response_model=list[schemas.BatchOut], tags=["supplier"])
def list_batches(product_id: int, p: Supplier, s: DB):
    return _own_product(s, product_id, p).batches


@app.post("/products/{product_id}/batches", response_model=schemas.BatchOut, status_code=201, tags=["supplier"])
def receive_batch(product_id: int, body: schemas.BatchCreate, p: Supplier, s: DB):
    product = _own_product(s, product_id, p)
    if body.expiry_date <= date.today():
        raise HTTPException(400, "Cannot receive stock that has already expired")
    batch = s.scalar(select(Batch).where(Batch.product_id == product.id, Batch.batch_number == body.batch_number))
    if batch:
        if batch.expiry_date != body.expiry_date:
            raise HTTPException(409, "This batch number already exists with a different expiry date")
        batch.quantity_available += body.quantity
    else:
        batch = Batch(product_id=product.id, batch_number=body.batch_number,
                      expiry_date=body.expiry_date, quantity_available=body.quantity)
        s.add(batch)
        s.flush()
    stock.record(s, batch, body.quantity, MovementReason.RECEIVED, user_id=p.user_id)
    s.commit()
    return batch


@app.post("/batches/{batch_id}/adjustments", response_model=schemas.BatchOut, tags=["supplier"])
def adjust_batch(batch_id: int, body: schemas.StockAdjustment, p: Supplier, s: DB):
    batch = s.get(Batch, batch_id)
    if not batch or batch.product.supplier_org_id != p.org_id:
        raise HTTPException(404, "Batch not found")
    if body.change == 0:
        raise HTTPException(400, "Adjustment cannot be zero")
    if batch.quantity_available + body.change < 0:
        raise HTTPException(400, f"Only {batch.quantity_available} units are available to remove")
    batch.quantity_available += body.change
    stock.record(s, batch, body.change, body.reason, note=body.note, user_id=p.user_id)
    s.commit()
    return batch


@app.get("/batches/{batch_id}/movements", response_model=list[schemas.MovementOut], tags=["supplier"])
def batch_movements(batch_id: int, p: Supplier, s: DB):
    batch = s.get(Batch, batch_id)
    if not batch or batch.product.supplier_org_id != p.org_id:
        raise HTTPException(404, "Batch not found")
    return s.scalars(select(StockMovement).where(StockMovement.batch_id == batch_id)
                     .order_by(StockMovement.id.desc())).all()


@app.get("/inventory/alerts", response_model=schemas.InventoryAlerts, tags=["supplier"])
def inventory_alerts(p: Supplier, s: DB, days: int = Query(settings.expiry_alert_days, ge=1, le=730)):
    today = date.today()
    rows = s.execute(
        select(Batch, Product.name).join(Product)
        .where(Product.supplier_org_id == p.org_id, Batch.quantity_available > 0,
               Batch.expiry_date <= today + timedelta(days=days))
        .order_by(Batch.expiry_date)
    ).all()
    expiring, expired = [], []
    for batch, name in rows:
        item = {"batch_id": batch.id, "product_id": batch.product_id, "product_name": name,
                "batch_number": batch.batch_number, "expiry_date": batch.expiry_date,
                "days_to_expiry": (batch.expiry_date - today).days,
                "quantity_available": batch.quantity_available}
        (expired if batch.expiry_date <= today else expiring).append(item)

    products = s.scalars(select(Product).where(Product.supplier_org_id == p.org_id,
                                               Product.is_active.is_(True), Product.reorder_level > 0)).all()
    summary = stock.stock_summary(s, [x.id for x in products])
    low = [{"product_id": x.id, "product_name": x.name, "stock_available": summary.get(x.id, (0, None))[0],
            "reorder_level": x.reorder_level}
           for x in products if summary.get(x.id, (0, None))[0] <= x.reorder_level]
    return {"expiring": expiring, "expired": expired, "low_stock": low}


# ---------------------------------------------------------------- internal (orders service only)
@app.get("/internal/products", response_model=list[schemas.InternalProduct], tags=["internal"],
         dependencies=[Depends(require_service)])
def internal_products(s: DB, ids: str = Query(..., description="Comma separated product ids")):
    id_list = [int(i) for i in ids.split(",") if i.strip().isdigit()]
    return s.scalars(select(Product).where(Product.id.in_(id_list))).all()


@app.post("/internal/reservations", response_model=schemas.ReservationResult, tags=["internal"],
          dependencies=[Depends(require_service)])
def create_reservation(body: schemas.ReservationRequest, s: DB):
    lines = stock.reserve(s, body.order_ref, [(l.product_id, l.quantity) for l in body.lines])
    return {"order_ref": body.order_ref, "lines": lines}


@app.post("/internal/reservations/{order_ref}/release", tags=["internal"], dependencies=[Depends(require_service)])
def release_reservation(order_ref: str, s: DB):
    return {"released": stock.release(s, order_ref)}


@app.post("/internal/reservations/{order_ref}/commit", tags=["internal"], dependencies=[Depends(require_service)])
def commit_reservation(order_ref: str, s: DB):
    return {"committed": stock.commit(s, order_ref)}
