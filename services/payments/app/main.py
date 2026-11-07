import asyncio
import logging
import uuid
from decimal import Decimal
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path
from typing import Annotated

from fastapi import Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from starlette.concurrency import run_in_threadpool

from multistock_common.app import create_app
from multistock_common.auth import CurrentUser, OrgType, Principal, Role, require_org
from multistock_common.db import Database
from multistock_common.events import EventPublisher

from . import schemas
from .config import settings
from .crypto import SecretBox, mask
from .models import MOBILE, MerchantAccount, Method, Payment, PayStatus, ProofOfPayment
from .paynow import PaynowClient, PaynowError, parse, to_status, verify
from .service import (UNPAYABLE_ORDER_STATUSES, OrdersClient, apply_provider_status, bank_ready, new_reference,
                      normalise_phone, now, paynow_ready, record, safe_poll_url, transition)
from .timeutil import as_utc

log = logging.getLogger("payments")

db = Database(settings.database_url)
events = EventPublisher(settings.redis_url, settings.event_stream, "payments",
                        settings.event_webhook_url, settings.service_token)
box = SecretBox(settings.payments_secret_key)
_orders = OrdersClient(settings.orders_url, settings.service_token)
_paynow = PaynowClient(settings.paynow_base_url)
UPLOADS = Path(settings.upload_dir)
ALLOWED_FILES = {b"%PDF": "application/pdf", b"\x89PNG": "image/png", b"\xff\xd8\xff": "image/jpeg"}
IN_PROGRESS_WINDOW = timedelta(minutes=15)


def get_orders() -> OrdersClient:
    return _orders


def get_paynow() -> PaynowClient:
    return _paynow


async def poller() -> None:
    while True:
        await asyncio.sleep(settings.poll_interval_seconds)
        try:
            await run_in_threadpool(poll_pending)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("payment poller failed")


def poll_pending(orders: OrdersClient | None = None, paynow: PaynowClient | None = None) -> int:
    """Callbacks can be lost (or can't reach a dev machine), so settle pending Paynow payments by polling."""
    orders, paynow = orders or get_orders(), paynow or get_paynow()
    settled = 0
    with db.SessionLocal() as s:
        pending = s.scalars(select(Payment).where(Payment.status == PayStatus.PENDING,
                                                  Payment.method != Method.BANK_TRANSFER)).all()
        for p in pending:
            if now() - as_utc(p.created_at) > timedelta(hours=settings.pending_timeout_hours):
                p.error = "No confirmation from Paynow in time"
                settled += transition(s, p, PayStatus.FAILED, "system", orders, events, reason="expired")
                continue
            acct = s.get(MerchantAccount, p.merchant_account_id) if p.merchant_account_id else None
            if not (p.poll_url and paynow_ready(acct)):
                continue
            try:
                st = paynow.poll(p.poll_url, box.decrypt(acct.paynow_integration_key_enc))
            except (PaynowError, ValueError) as exc:
                log.warning("poll failed for %s: %s", p.reference, exc)
                continue
            settled += apply_provider_status(s, p, st, "poll", orders, events)
    return settled


@asynccontextmanager
async def lifespan(_app):
    db.create_all()
    UPLOADS.mkdir(parents=True, exist_ok=True)
    task = asyncio.create_task(poller()) if settings.poll_interval_seconds > 0 else None
    yield
    if task:
        task.cancel()


app = create_app(settings, "Payments Service")
app.router.lifespan_context = lifespan
DB = Annotated[Session, Depends(db.session)]
Orders = Annotated[OrdersClient, Depends(get_orders)]
Paynow = Annotated[PaynowClient, Depends(get_paynow)]
Supplier = Annotated[Principal, require_org(OrgType.SUPPLIER)]
Pharmacy = Annotated[Principal, require_org(OrgType.PHARMACY)]


# ---------------------------------------------------------------- supplier: where money goes
def _merchant_out(a: MerchantAccount | None, currency: str) -> dict:
    key = None
    if a and a.paynow_integration_key_enc:
        try:
            key = mask(box.decrypt(a.paynow_integration_key_enc))
        except ValueError:
            key = "•••• (unreadable, re-enter)"
    return {"currency": currency, "paynow_enabled": bool(a and a.paynow_enabled),
            "paynow_integration_id": a.paynow_integration_id if a else None, "paynow_integration_key_masked": key,
            **{k: getattr(a, k) if a else None for k in ("bank_name", "bank_account_name", "bank_account_number",
                                                          "bank_branch", "payment_instructions")}}


@app.get("/merchant-accounts", response_model=list[schemas.MerchantOut], tags=["supplier"])
def my_accounts(p: Supplier, s: DB):
    rows = {a.currency: a for a in s.scalars(select(MerchantAccount).where(MerchantAccount.supplier_org_id == p.org_id))}
    return [_merchant_out(rows.get(c), c) for c in ("USD", "ZWG")] + \
        [_merchant_out(a, c) for c, a in rows.items() if c not in ("USD", "ZWG")]


@app.put("/merchant-accounts/{currency}", response_model=schemas.MerchantOut, tags=["supplier"])
def save_account(currency: str, body: schemas.MerchantIn, p: Supplier, s: DB):
    currency = currency.upper()
    if currency not in ("USD", "ZWG", "ZAR"):
        raise HTTPException(422, "Currency must be USD, ZWG or ZAR")
    if p.role == Role.STAFF:
        raise HTTPException(403, "Only owners and managers can change where payments go")
    a = s.scalar(select(MerchantAccount).where(MerchantAccount.supplier_org_id == p.org_id,
                                               MerchantAccount.currency == currency))
    if a is None:
        a = MerchantAccount(supplier_org_id=p.org_id, currency=currency)
        s.add(a)
    data = body.model_dump(exclude={"paynow_integration_key"})
    for k, v in data.items():
        setattr(a, k, v.strip() if isinstance(v, str) else v)
    if body.paynow_integration_key:
        a.paynow_integration_key_enc = box.encrypt(body.paynow_integration_key.strip())
    if a.paynow_enabled and not (a.paynow_integration_id and a.paynow_integration_key_enc):
        raise HTTPException(422, "Enter the Paynow integration ID and key to turn on Paynow")
    s.commit()
    return _merchant_out(a, currency)


# ---------------------------------------------------------------- paying an order
def _order_for(orders: OrdersClient, order_number: str, p: Principal) -> dict:
    o = orders.get(order_number)
    if p.org_id not in (o["pharmacy_org_id"], o["supplier_org_id"]) and not p.is_platform_admin:
        raise HTTPException(404, "Order not found")
    return o


def _account(s: Session, supplier_org_id: int, currency: str) -> MerchantAccount | None:
    return s.scalar(select(MerchantAccount).where(MerchantAccount.supplier_org_id == supplier_org_id,
                                                  MerchantAccount.currency == currency))


@app.get("/orders/{order_number}/options", response_model=schemas.PaymentOptions, tags=["payments"])
def payment_options(order_number: str, p: CurrentUser, s: DB, orders: Orders):
    o = _order_for(orders, order_number, p)
    acct = _account(s, o["supplier_org_id"], o["currency"])
    methods, reason = [], None
    if o["status"] in UNPAYABLE_ORDER_STATUSES:
        reason = f"This order was {o['status'].lower()}, so it doesn't need paying."
    elif o.get("payment_status") == "PAID":
        reason = "This order is paid."
    else:
        if paynow_ready(acct):
            methods += [Method.ECOCASH, Method.ONEMONEY, Method.INNBUCKS, Method.PAYNOW_WEB]
        if bank_ready(acct):
            methods.append(Method.BANK_TRANSFER)
        if not methods:
            reason = f"{o['supplier_name']} hasn't set up online payments for {o['currency']} yet. Pay as agreed with them."
    bank = schemas.BankDetails.model_validate(acct, from_attributes=True) if bank_ready(acct) else None
    return {"order_number": order_number, "amount": o["subtotal"], "currency": o["currency"],
            "payment_status": o.get("payment_status"), "methods": methods, "bank": bank, "reason": reason}


def _load(s: Session, payment_id: int, p: Principal) -> Payment:
    pay = s.scalar(select(Payment).options(selectinload(Payment.proofs)).where(Payment.id == payment_id))
    if not pay or p.org_id not in (pay.pharmacy_org_id, pay.supplier_org_id):
        raise HTTPException(404, "Payment not found")
    return pay


def _check_payable(s: Session, o: dict) -> None:
    if o["status"] in UNPAYABLE_ORDER_STATUSES:
        raise HTTPException(409, f"This order was {o['status'].lower()}; it can't be paid")
    if o.get("payment_status") == "PAID":
        raise HTTPException(409, "This order is already paid")
    busy = s.scalars(select(Payment).where(Payment.order_number == o["order_number"],
                                           Payment.status == PayStatus.PENDING)).all()
    if any(now() - as_utc(b.created_at) < IN_PROGRESS_WINDOW for b in busy):
        raise HTTPException(409, "A payment for this order is already in progress. Approve it on your phone, "
                                 "or wait a few minutes and try again.")


@app.post("/payments", response_model=schemas.PaymentOut, status_code=201, tags=["payments"])
def start_payment(body: schemas.PaymentIn, p: Pharmacy, s: DB, orders: Orders, paynow: Paynow):
    if body.method == Method.BANK_TRANSFER:
        raise HTTPException(422, "For bank transfers, upload your proof of payment instead")
    o = _order_for(orders, body.order_number, p)
    if o["pharmacy_org_id"] != p.org_id:
        raise HTTPException(403, "Only the ordering pharmacy can pay this order")
    _check_payable(s, o)
    acct = _account(s, o["supplier_org_id"], o["currency"])
    if not paynow_ready(acct):
        raise HTTPException(409, f"{o['supplier_name']} doesn't accept Paynow payments in {o['currency']} yet")
    phone = normalise_phone(body.phone or "") if body.method in MOBILE else None
    pay = Payment(reference=new_reference(), order_id=o["id"], order_number=o["order_number"],
                  pharmacy_org_id=o["pharmacy_org_id"], supplier_org_id=o["supplier_org_id"],
                  merchant_account_id=acct.id, amount=Decimal(str(o["subtotal"])), currency=o["currency"], method=body.method,
                  phone=phone, created_by_user_id=p.user_id, created_by_name=p.name, status=PayStatus.CREATED)
    s.add(pay)
    s.commit()
    base = settings.public_base_url.rstrip("/")
    try:
        res = paynow.initiate(
            integration_id=acct.paynow_integration_id, integration_key=box.decrypt(acct.paynow_integration_key_enc),
            reference=pay.reference, amount=f"{pay.amount:.2f}", info=pay.order_number,
            return_url=f"{base}/orders/{pay.order_id}?payment={pay.reference}",
            result_url=f"{base}/api/payments/paynow/result/{pay.reference}",
            auth_email=p.email, phone=phone, method=body.method.value if phone else None)
    except (PaynowError, ValueError) as exc:
        pay.error = str(exc)[:500]
        transition(s, pay, PayStatus.FAILED, "initiate", orders, events, error=pay.error)
        raise HTTPException(502, str(exc))
    pay.poll_url = safe_poll_url(res.poll_url, settings.paynow_base_url)
    pay.redirect_url, pay.instructions = res.redirect_url, res.instructions
    pay.innbucks_code, pay.innbucks_expires = res.innbucks_code, res.innbucks_expires
    transition(s, pay, PayStatus.PENDING, "initiate", orders, events)
    return _load(s, pay.id, p)


@app.post("/payments/{payment_id}/refresh", response_model=schemas.PaymentOut, tags=["payments"])
def refresh(payment_id: int, p: CurrentUser, s: DB, orders: Orders, paynow: Paynow):
    pay = _load(s, payment_id, p)
    acct = s.get(MerchantAccount, pay.merchant_account_id) if pay.merchant_account_id else None
    if pay.status == PayStatus.PENDING and pay.poll_url and paynow_ready(acct):
        try:
            st = paynow.poll(pay.poll_url, box.decrypt(acct.paynow_integration_key_enc))
            apply_provider_status(s, pay, st, "poll", orders, events)
        except (PaynowError, ValueError) as exc:
            log.warning("refresh failed for %s: %s", pay.reference, exc)
    return _load(s, payment_id, p)


@app.get("/payments", response_model=list[schemas.PaymentOut], tags=["payments"])
def list_payments(order_number: str, p: CurrentUser, s: DB):
    return s.scalars(select(Payment).options(selectinload(Payment.proofs))
                     .where(Payment.order_number == order_number,
                            (Payment.pharmacy_org_id == p.org_id) | (Payment.supplier_org_id == p.org_id))
                     .order_by(Payment.id.desc())).all()


# ---------------------------------------------------------------- Paynow result URL (server-to-server)
@app.post("/paynow/result/{reference}", response_class=PlainTextResponse, tags=["paynow"])
async def paynow_result(reference: str, request: Request):
    """Paynow posts the transaction status here. The body is trusted only if its hash verifies with the
    supplier's integration key and the reference and amount match what we sent."""
    fields = parse((await request.body()).decode("utf-8", "replace"))
    with db.SessionLocal() as s:
        pay = s.scalar(select(Payment).where(Payment.reference == reference))
        acct = s.get(MerchantAccount, pay.merchant_account_id) if pay and pay.merchant_account_id else None
        if not pay or not paynow_ready(acct):
            raise HTTPException(404, "Unknown payment")
        if not verify(fields, box.decrypt(acct.paynow_integration_key_enc)):
            log.warning("rejected Paynow result for %s: hash mismatch", reference)
            record(s, pay, "REJECTED_CALLBACK", "callback", reason="hash mismatch")
            s.commit()
            raise HTTPException(403, "Invalid hash")
        data = {k.lower(): v for k, v in fields}
        if data.get("pollurl"):
            pay.poll_url = safe_poll_url(data["pollurl"], settings.paynow_base_url) or pay.poll_url
        await run_in_threadpool(apply_provider_status, s, pay, to_status(data), "callback", get_orders(), events)
    return "OK"


# ---------------------------------------------------------------- bank transfer: proof of payment
def _sniff(head: bytes) -> str | None:
    return next((ct for magic, ct in ALLOWED_FILES.items() if head.startswith(magic)), None)


@app.post("/payments/proof", response_model=schemas.PaymentOut, status_code=201, tags=["payments"])
async def upload_proof(p: Pharmacy, s: DB, orders: Orders, order_number: str = Form(..., max_length=40),
                       bank_reference: str | None = Form(None, max_length=100), file: UploadFile = File(...)):
    content = await file.read(settings.max_upload_bytes + 1)
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(413, "The file is larger than 5 MB")
    ctype = _sniff(content[:8])
    if not ctype:
        raise HTTPException(422, "Upload a PDF, JPG or PNG of the bank confirmation")
    o = await run_in_threadpool(_order_for, orders, order_number, p)
    if o["pharmacy_org_id"] != p.org_id:
        raise HTTPException(403, "Only the ordering pharmacy can upload proof of payment")
    if o["status"] in UNPAYABLE_ORDER_STATUSES or o.get("payment_status") == "PAID":
        raise HTTPException(409, "This order doesn't need paying")
    pay = s.scalar(select(Payment).where(Payment.order_number == order_number,
                                         Payment.method == Method.BANK_TRANSFER,
                                         Payment.status == PayStatus.AWAITING_CONFIRMATION))
    if pay is None:
        acct = _account(s, o["supplier_org_id"], o["currency"])
        pay = Payment(reference=new_reference(), order_id=o["id"], order_number=order_number,
                      pharmacy_org_id=o["pharmacy_org_id"], supplier_org_id=o["supplier_org_id"],
                      merchant_account_id=acct.id if acct else None, amount=Decimal(str(o["subtotal"])), currency=o["currency"],
                      method=Method.BANK_TRANSFER, created_by_user_id=p.user_id, created_by_name=p.name,
                      status=PayStatus.CREATED)
        s.add(pay)
        s.flush()
    stored = f"{uuid.uuid4().hex}{'.pdf' if ctype.endswith('pdf') else '.' + ctype.split('/')[1]}"
    (UPLOADS / stored).write_bytes(content)
    s.add(ProofOfPayment(payment_id=pay.id, filename=(file.filename or stored)[:255], stored_as=stored,
                         content_type=ctype, size=len(content), bank_reference=bank_reference, uploaded_by=p.name))
    s.commit()
    if pay.status != PayStatus.AWAITING_CONFIRMATION:
        await run_in_threadpool(transition, s, pay, PayStatus.AWAITING_CONFIRMATION, "pharmacy", orders, events)
    return _load(s, pay.id, p)


@app.get("/payments/{payment_id}/proofs/{proof_id}", tags=["payments"])
def download_proof(payment_id: int, proof_id: int, p: CurrentUser, s: DB):
    pay = _load(s, payment_id, p)
    proof = next((x for x in pay.proofs if x.id == proof_id), None)
    if not proof or not (UPLOADS / proof.stored_as).is_file():
        raise HTTPException(404, "File not found")
    return FileResponse(UPLOADS / proof.stored_as, media_type=proof.content_type, filename=proof.filename)


@app.post("/payments/{payment_id}/review", response_model=schemas.PaymentOut, tags=["payments"])
def review_proof(payment_id: int, body: schemas.Review, p: Supplier, s: DB, orders: Orders):
    pay = _load(s, payment_id, p)
    if pay.supplier_org_id != p.org_id:
        raise HTTPException(403, "Only the supplier can confirm this payment")
    if pay.status != PayStatus.AWAITING_CONFIRMATION:
        raise HTTPException(409, "This payment isn't waiting for confirmation")
    if not body.accept and not body.note:
        raise HTTPException(422, "Tell the pharmacy why the proof was rejected")
    for proof in pay.proofs:
        proof.reviewed_by, proof.review_note = proof.reviewed_by or p.name, proof.review_note or body.note
    pay.note = body.note
    transition(s, pay, PayStatus.PAID if body.accept else PayStatus.REJECTED, "supplier", orders, events,
               by=p.name, note=body.note)
    return _load(s, payment_id, p)
