from app.handlers import handle_event
from app.main import db
from tests.conftest import OTHER_SUPPLIER, PHARMACY, SUPPLIER, token

ORDER = {"order_id": 7, "order_number": "PO-1", "status": "SUBMITTED", "pharmacy_org_id": 20,
         "pharmacy_name": "Avenues Pharmacy", "supplier_org_id": 10, "supplier_name": "Pharma Wholesale",
         "subtotal": "35.00", "currency": "USD"}


def test_order_events_become_notifications_with_per_user_read_state(client):
    with db.SessionLocal() as s:
        handle_event(s, {"type": "order.created", "payload": ORDER})
        handle_event(s, {"type": "order.status_changed", "payload": {
            **ORDER, "status": "REJECTED", "note": "No stock", "changed_by_org_type": "SUPPLIER"}})

    supplier_items = client.get("/notifications", headers=SUPPLIER).json()
    assert supplier_items[0]["title"] == "New order PO-1" and supplier_items[0]["link"] == "/orders/7"
    pharmacy_items = client.get("/notifications", headers=PHARMACY).json()
    assert pharmacy_items[0]["title"] == "Order PO-1 was rejected"
    assert "No stock" in pharmacy_items[0]["body"]

    client.post(f"/notifications/{pharmacy_items[0]['id']}/read", headers=PHARMACY)
    assert client.get("/unread", headers=PHARMACY).json()["notifications"] == 0
    colleague = token(5, 20, "PHARMACY", "Avenues Pharmacy", role="STAFF")
    assert client.get("/unread", headers=colleague).json()["notifications"] == 1
    # other organisations can't touch it
    assert client.post(f"/notifications/{pharmacy_items[0]['id']}/read", headers=SUPPLIER).status_code == 404


def test_messaging_between_pharmacy_and_supplier(client):
    r = client.post("/conversations", headers=PHARMACY, json={
        "counterpart_org_id": 10, "counterpart_org_name": "Pharma Wholesale",
        "subject": "Insulin availability", "body": "Do you have Mixtard in stock?"})
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    assert client.get("/unread", headers=SUPPLIER).json()["messages"] == 1
    sup_convs = client.get("/conversations", headers=SUPPLIER).json()
    assert sup_convs[0]["counterpart_name"] == "Avenues Pharmacy"

    client.get(f"/conversations/{cid}/messages", headers=SUPPLIER)
    assert client.get("/unread", headers=SUPPLIER).json()["messages"] == 0
    client.post(f"/conversations/{cid}/messages", headers=SUPPLIER, json={"body": "Yes, 40 pens."})
    msgs = client.get(f"/conversations/{cid}/messages", headers=PHARMACY).json()
    assert [m["body"] for m in msgs] == ["Do you have Mixtard in stock?", "Yes, 40 pens."]
    assert client.get(f"/conversations/{cid}/messages", headers=OTHER_SUPPLIER).status_code == 404


def test_broadcast_audiences(client):
    assert client.post("/broadcasts", headers=PHARMACY, json={"title": "Hi", "body": "There"}).status_code == 403
    assert client.post("/broadcasts", headers=SUPPLIER, json={"title": "Hi", "body": "Hello all", "audience": "ALL"}).status_code == 403
    client.post("/broadcasts", headers=SUPPLIER, json={"title": "Price drop", "body": "Amoxil now $11"})
    assert [b["title"] for b in client.get("/broadcasts", headers=PHARMACY).json()] == ["Price drop"]
    assert client.get("/broadcasts", headers=OTHER_SUPPLIER).json() == []


def test_websocket_requires_valid_token(client):
    import pytest
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws?token=garbage") as ws:
            ws.receive_text()
    good = PHARMACY["Authorization"][7:]
    with client.websocket_connect(f"/ws?token={good}") as ws:
        ws.send_text("ping")


def test_agent_alerts_become_notifications(client):
    with db.SessionLocal() as s:
        handle_event(s, {"type": "agent.alert", "payload": {"org_id": 10, "severity": "critical", "alert_id": 3,
                                                            "title": "Amoxil is out of stock", "body": "No stock left.",
                                                            "link": "/inventory/1"}})
    [n] = client.get("/notifications", headers=SUPPLIER).json()
    assert n["title"] == "Urgent: Amoxil is out of stock" and n["link"] == "/inventory/1" and n["kind"] == "insight"
    assert client.get("/notifications", headers=PHARMACY).json() == []


def test_payment_events_notify_both_sides(client):
    pay = {"order_id": 7, "order_number": "PO-1", "pharmacy_org_id": 20, "supplier_org_id": 10, "amount": "536.00",
           "currency": "ZWG", "method": "ecocash", "note": None}
    with db.SessionLocal() as s:
        handle_event(s, {"type": "payment.paid", "payload": pay})
        handle_event(s, {"type": "payment.pending", "payload": pay})  # no notification for in-progress
    [sup] = client.get("/notifications", headers=SUPPLIER).json()
    assert sup["title"] == "Payment received for PO-1" and sup["body"] == "ZiG 536.00 via EcoCash."
    assert client.get("/notifications", headers=PHARMACY).json()[0]["title"] == "Payment confirmed for PO-1"
