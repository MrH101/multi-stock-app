"""Payment rules shared by the API, the Paynow callback and the background poller."""
import logging
import re
import secrets
from datetime import datetime, timezone
from decimal import Decimal
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException
from sqlalchemy.orm import Session

from multistock_common.events import EventPublisher

from .models import FINAL, MerchantAccount, Method, Payment, PaymentEvent, PayStatus
from .paynow import (CANCELLED_STATUSES, DISPUTED_STATUSES, FAILED_STATUSES, PAID_STATUSES, REFUNDED_STATUSES,
                     StatusResult)

log = logging.getLogger("payments")

# What the orders service shows on the PO for each of our states.
ORDER_PAYMENT_STATUS = {
    PayStatus.PENDING: "PENDING", PayStatus.AWAITING_CONFIRMATION: "AWAITING_CONFIRMATION",
    PayStatus.PAID: "PAID", PayStatus.REFUNDED: "REFUNDED",
    PayStatus.FAILED: "UNPAID", PayStatus.CANCELLED: "UNPAID", PayStatus.REJECTED: "UNPAID",
}
UNPAYABLE_ORDER_STATUSES = {"REJECTED", "CANCELLED"}


def now() -> datetime:
    return datetime.now(timezone.utc)


def new_reference() -> str:
    return f"PAY-{secrets.token_hex(5).upper()}"


def normalise_phone(raw: str) -> str:
    """Zimbabwe mobile numbers in the local format Paynow expects (07XXXXXXXX)."""
    digits = re.sub(r"\D", "", raw or "")
    if digits.startswith("263"):
        digits = "0" + digits[3:]
    elif len(digits) == 9 and digits.startswith("7"):
        digits = "0" + digits
    if not re.fullmatch(r"07[1-8]\d{7}", digits):
        raise HTTPException(422, "Enter a Zimbabwe mobile number, e.g. 0771 234 567")
    return digits


def safe_poll_url(url: str | None, paynow_base: str) -> str | None:
    """Only ever call back to Paynow's own host (the poll URL comes from a response, so check it)."""
    if not url:
        return None
    base, u = urlparse(paynow_base), urlparse(url)
    return url if (u.scheme, u.hostname) == (base.scheme, base.hostname) else None


class OrdersClient:
    def __init__(self, base_url: str, service_token: str, transport: httpx.BaseTransport | None = None):
        self._http = httpx.Client(base_url=base_url, headers={"X-Service-Token": service_token},
                                  timeout=httpx.Timeout(10.0, connect=3.0), transport=transport)

    def get(self, order_number: str) -> dict:
        r = self._http.get(f"/internal/orders/{order_number}")
        if r.status_code == 404:
            raise HTTPException(404, "Order not found")
        r.raise_for_status()
        return r.json()

    def set_payment(self, order_number: str, status: str, via: str | None, paid_at: datetime | None) -> None:
        body = {"payment_status": status, "paid_via": via, "paid_at": paid_at.isoformat() if paid_at else None}
        for _ in range(3):
            try:
                self._http.post(f"/internal/orders/{order_number}/payment", json=body).raise_for_status()
                return
            except httpx.HTTPError as exc:
                log.warning("could not update order %s payment status: %s", order_number, exc)
        # The payment record stays authoritative; the poller re-syncs orders on its next pass.


def record(s: Session, p: Payment, status: str, source: str, **detail) -> None:
    s.add(PaymentEvent(payment_id=p.id, at=now(), status=status, source=source, detail=detail))


def transition(s: Session, p: Payment, new: PayStatus, source: str, orders: OrdersClient, events: EventPublisher,
               **detail) -> bool:
    """Move a payment to a new state once; repeated callbacks/polls with the same state are no-ops."""
    if p.status == new:
        return False
    if p.status in FINAL and not (p.status == PayStatus.PAID and new in (PayStatus.REFUNDED, PayStatus.DISPUTED)):
        log.info("ignoring %s -> %s for final payment %s", p.status, new, p.reference)
        return False
    previous = p.status
    p.status = new
    if new == PayStatus.PAID:
        p.paid_at = p.paid_at or now()
    record(s, p, new, source, previous=previous, **detail)
    s.commit()
    if new in ORDER_PAYMENT_STATUS:
        orders.set_payment(p.order_number, ORDER_PAYMENT_STATUS[new], p.method, p.paid_at)
    events.publish(f"payment.{new.lower()}", event_payload(p))
    return True


def apply_provider_status(s: Session, p: Payment, st: StatusResult, source: str, orders: OrdersClient,
                          events: EventPublisher) -> bool:
    p.provider_status = st.status
    if st.paynow_reference:
        p.provider_reference = st.paynow_reference
    if st.reference and st.reference != p.reference:
        record(s, p, "IGNORED", source, reason="reference mismatch", got=st.reference)
        s.commit()
        return False
    if st.status in PAID_STATUSES:
        if st.amount is not None and Decimal(st.amount).quantize(Decimal("0.01")) != p.amount:
            p.error = f"Paynow reported {st.amount}, expected {p.amount}"
            return transition(s, p, PayStatus.DISPUTED, source, orders, events, provider_status=st.status,
                              amount=st.amount)
        return transition(s, p, PayStatus.PAID, source, orders, events, provider_status=st.status,
                          paynow_reference=st.paynow_reference)
    if st.status in FAILED_STATUSES:
        return transition(s, p, PayStatus.FAILED, source, orders, events, provider_status=st.status)
    if st.status in CANCELLED_STATUSES:
        return transition(s, p, PayStatus.CANCELLED, source, orders, events, provider_status=st.status)
    if st.status in DISPUTED_STATUSES:
        return transition(s, p, PayStatus.DISPUTED, source, orders, events, provider_status=st.status)
    if st.status in REFUNDED_STATUSES:
        return transition(s, p, PayStatus.REFUNDED, source, orders, events, provider_status=st.status)
    s.commit()  # created / sent: still waiting for the customer
    return False


def event_payload(p: Payment) -> dict:
    return {"payment_id": p.id, "reference": p.reference, "order_id": p.order_id, "order_number": p.order_number,
            "pharmacy_org_id": p.pharmacy_org_id, "supplier_org_id": p.supplier_org_id, "amount": str(p.amount),
            "currency": p.currency, "method": p.method, "status": p.status, "note": p.note}


def paynow_ready(acct: MerchantAccount | None) -> bool:
    return bool(acct and acct.paynow_enabled and acct.paynow_integration_id and acct.paynow_integration_key_enc)


def bank_ready(acct: MerchantAccount | None) -> bool:
    return bool(acct and acct.bank_account_number)


METHOD_LABEL = {Method.ECOCASH: "EcoCash", Method.ONEMONEY: "OneMoney", Method.INNBUCKS: "InnBucks",
                Method.PAYNOW_WEB: "Card / ZimSwitch (Paynow)", Method.BANK_TRANSFER: "Bank transfer"}
