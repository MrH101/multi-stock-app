"""Turn domain events from other services into notifications."""
import logging

from sqlalchemy.orm import Session

from .models import Notification
from .realtime import manager

log = logging.getLogger("handlers")

STATUS_TEXT = {
    "ACCEPTED": "was accepted",
    "REJECTED": "was rejected",
    "DISPATCHED": "is on the way",
    "DELIVERED": "was delivered",
    "CANCELLED": "was cancelled",
}


def notify(s: Session, org_id: int, kind: str, title: str, body: str, link: str | None = None) -> Notification:
    n = Notification(org_id=org_id, kind=kind, title=title, body=body, link=link)
    s.add(n)
    s.commit()
    manager.push_threadsafe(org_id, {"kind": "notification", "id": n.id, "title": title, "body": body, "link": link})
    return n


METHOD = {"ecocash": "EcoCash", "onemoney": "OneMoney", "innbucks": "InnBucks", "paynow_web": "Paynow",
          "bank_transfer": "bank transfer"}


def _money(p: dict) -> str:
    return f"{'ZiG' if p['currency'] == 'ZWG' else p['currency']} {p['amount']}"


def handle_payment(s: Session, status: str, p: dict) -> None:
    link, num, via = f"/orders/{p['order_id']}", p["order_number"], METHOD.get(p.get("method"), p.get("method"))
    if status == "paid":
        notify(s, p["supplier_org_id"], "payment", f"Payment received for {num}", f"{_money(p)} via {via}.", link)
        notify(s, p["pharmacy_org_id"], "payment", f"Payment confirmed for {num}", f"{_money(p)} via {via}.", link)
    elif status == "awaiting_confirmation":
        notify(s, p["supplier_org_id"], "payment", f"Proof of payment for {num}",
               f"The pharmacy says it paid {_money(p)} by bank transfer. Please check and confirm.", link)
    elif status == "rejected":
        notify(s, p["pharmacy_org_id"], "payment", f"Proof of payment not accepted for {num}",
               f"The supplier couldn't match your transfer.{' ' + p['note'] if p.get('note') else ''}", link)
    elif status in ("failed", "cancelled"):
        notify(s, p["pharmacy_org_id"], "payment", f"Payment {status} for {num}",
               f"Your {via} payment of {_money(p)} didn't go through. You can try again from the order.", link)
    elif status == "disputed":
        notify(s, p["supplier_org_id"], "payment", f"Payment for {num} needs checking",
               "Paynow reported a dispute or an amount that doesn't match the order.", link)


def handle_event(s: Session, event: dict) -> None:
    kind, p = event.get("type"), event.get("payload", {})
    if kind == "order.created":
        notify(s, p["supplier_org_id"], "order", f"New order {p['order_number']}",
               f"{p['pharmacy_name']} placed an order worth {p['currency']} {p['subtotal']}.",
               f"/orders/{p['order_id']}")
    elif kind == "order.status_changed":
        status = p["status"]
        text = STATUS_TEXT.get(status, f"is now {status.lower()}")
        note = f" Note: {p['note']}" if p.get("note") else ""
        if p.get("changed_by_org_type") == "SUPPLIER":
            notify(s, p["pharmacy_org_id"], "order", f"Order {p['order_number']} {text}",
                   f"{p['supplier_name']} updated your order.{note}", f"/orders/{p['order_id']}")
        else:
            notify(s, p["supplier_org_id"], "order", f"Order {p['order_number']} {text}",
                   f"{p['pharmacy_name']} updated the order.{note}", f"/orders/{p['order_id']}")
    elif kind.startswith("payment."):
        handle_payment(s, kind.split(".", 1)[1], p)
    elif kind == "agent.alert":
        # Raised by the monitoring agent (stock, expiry, budget, order SLA, platform health).
        prefix = {"critical": "Urgent: ", "warning": ""}.get(p.get("severity", ""), "")
        notify(s, p["org_id"], "insight", f"{prefix}{p['title']}"[:200], p["body"][:1000], p.get("link"))
    else:
        log.debug("ignoring event %s", kind)
