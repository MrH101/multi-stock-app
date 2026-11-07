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
    elif kind == "agent.alert":
        # Raised by the monitoring agent (stock, expiry, budget, order SLA, platform health).
        prefix = {"critical": "Urgent: ", "warning": ""}.get(p.get("severity", ""), "")
        notify(s, p["org_id"], "insight", f"{prefix}{p['title']}"[:200], p["body"][:1000], p.get("link"))
    else:
        log.debug("ignoring event %s", kind)
