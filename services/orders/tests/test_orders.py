from app.main import events
from tests.conftest import OTHER_SUPPLIER, PHARMACY, SUPPLIER, token

DELIVERY = {"delivery_address": "12 Samora Machel Ave, Harare", "contact_name": "Tendai Moyo",
            "contact_phone": "+263771234567"}


def checkout(client, lines, **extra):
    return client.post("/orders/checkout", headers=PHARMACY, json={"lines": lines, **DELIVERY, **extra})


def test_checkout_splits_one_order_per_supplier(client, catalog):
    r = checkout(client, [{"product_id": 1, "quantity": 2}, {"product_id": 2, "quantity": 5},
                          {"product_id": 3, "quantity": 1}])
    assert r.status_code == 201, r.text
    orders = sorted(r.json(), key=lambda o: o["supplier_org_id"])
    assert [o["supplier_name"] for o in orders] == ["Pharma Wholesale", "Other Wholesale"]
    assert orders[0]["subtotal"] == "35.00"
    assert orders[0]["lines"][0]["allocations"][0]["batch_number"] == "B1"
    assert orders[0]["allowed_transitions"] == ["CANCELLED"]
    assert [e["type"] for e in events.published[-2:]] == ["order.created", "order.created"]

    # each party only sees its own orders
    assert client.get("/orders", headers=SUPPLIER).json()["total"] == 1
    assert client.get("/orders", headers=OTHER_SUPPLIER).json()["total"] == 1
    assert client.get("/orders", headers=PHARMACY).json()["total"] == 2
    assert client.get(f"/orders/{orders[1]['id']}", headers=SUPPLIER).status_code == 404


def test_failed_reservation_releases_earlier_suppliers(client, catalog):
    r = checkout(client, [{"product_id": 1, "quantity": 2}, {"product_id": 3, "quantity": 50}])
    assert r.status_code == 409
    assert catalog.stock[1]["qty"] == 100  # compensated
    assert client.get("/orders", headers=PHARMACY).json()["total"] == 0


def test_idempotent_checkout(client, catalog):
    first = checkout(client, [{"product_id": 1, "quantity": 2}], idempotency_key="cart-abc").json()
    second = checkout(client, [{"product_id": 1, "quantity": 2}], idempotency_key="cart-abc").json()
    assert first[0]["id"] == second[0]["id"]
    assert catalog.stock[1]["qty"] == 98


def test_status_workflow_and_stock_side_effects(client, catalog):
    order = checkout(client, [{"product_id": 1, "quantity": 10}]).json()[0]
    oid, ref = order["id"], order["order_number"]

    # pharmacy cannot accept its own order; supplier cannot deliver before dispatch
    assert client.post(f"/orders/{oid}/status", headers=PHARMACY, json={"status": "ACCEPTED"}).status_code == 409
    assert client.post(f"/orders/{oid}/status", headers=SUPPLIER, json={"status": "DELIVERED"}).status_code == 409

    r = client.post(f"/orders/{oid}/status", headers=SUPPLIER, json={"status": "ACCEPTED"})
    assert r.json()["allowed_transitions"] == ["DISPATCHED", "CANCELLED"]
    client.post(f"/orders/{oid}/status", headers=SUPPLIER, json={"status": "DISPATCHED"})
    assert ("commit", ref) in catalog.calls
    r = client.post(f"/orders/{oid}/status", headers=PHARMACY, json={"status": "DELIVERED", "note": "All received"})
    assert r.json()["status"] == "DELIVERED"
    assert [h["status"] for h in r.json()["history"]] == ["SUBMITTED", "ACCEPTED", "DISPATCHED", "DELIVERED"]


def test_reject_requires_reason_and_returns_stock(client, catalog):
    oid = checkout(client, [{"product_id": 1, "quantity": 10}]).json()[0]["id"]
    assert client.post(f"/orders/{oid}/status", headers=SUPPLIER, json={"status": "REJECTED"}).status_code == 400
    r = client.post(f"/orders/{oid}/status", headers=SUPPLIER, json={"status": "REJECTED", "note": "Out of cold chain capacity"})
    assert r.status_code == 200
    assert catalog.stock[1]["qty"] == 100


def test_budget_tracks_committed_spend(client):
    staff = token(4, 20, "PHARMACY", "Avenues Pharmacy", role="STAFF")
    assert client.put("/budget", headers=staff, json={"amount": "1000"}).status_code == 403
    assert client.put("/budget", headers=SUPPLIER, json={"amount": "1000"}).status_code == 403
    client.put("/budget", headers=PHARMACY, json={"amount": "1000.00", "currency": "usd"})
    checkout(client, [{"product_id": 1, "quantity": 8}])  # 100.00
    oid = checkout(client, [{"product_id": 2, "quantity": 10}]).json()[0]["id"]  # 20.00
    client.post(f"/orders/{oid}/status", headers=PHARMACY, json={"status": "CANCELLED"})
    b = client.get("/budget", headers=staff).json()
    assert (b["committed"], b["remaining"], b["percent_used"]) == ("100.00", "900.00", 10.0)

    summary = client.get("/orders/summary", headers=PHARMACY).json()
    assert summary["open_orders"] == 1 and summary["counts"]["CANCELLED"] == 1
    assert summary["month_total"] == "100.00" and len(summary["monthly"]) == 6
    assert summary["top_products"][0]["product_name"] == "Amoxil 500mg"
