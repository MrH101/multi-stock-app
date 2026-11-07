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
    assert orders[0]["lines"][0]["schedule"] == "PP" and orders[0]["lines"][0]["mcaz_registration_number"] == "MCAZ-1"
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


def test_monitoring_snapshot(client, catalog):
    from tests.conftest import SERVICE
    client.put("/budget", headers=PHARMACY, json={"amount": "100.00", "currency": "USD"})
    checkout(client, [{"product_id": 1, "quantity": 2}])
    checkout(client, [{"product_id": 1, "quantity": 1}])

    assert client.get("/internal/monitoring/snapshot").status_code == 403
    snap = client.get("/internal/monitoring/snapshot", headers=SERVICE).json()
    [budget] = snap["budgets"]
    assert budget["pharmacy_org_id"] == 20 and budget["committed"] == "37.50" and budget["days_in_month"] >= 28
    assert len(snap["open_orders"]) == 2 and all(o["status"] == "SUBMITTED" for o in snap["open_orders"])
    assert snap["open_orders"][0]["status_since"]
    [demand] = snap["demand"]
    assert demand == {"pharmacy_org_id": 20, "supplier_org_id": 10, "product_id": 1, "product_name": "Amoxil 500mg",
                      "quantity": 3, "order_count": 2}


ADMIN = token(99, 1, "PLATFORM", "Multi-Stock Platform")


def set_rates(client, **rates):
    return client.put("/admin/fx/rates", headers=ADMIN, json={"rates": rates, "source": "RBZ interbank"})


def test_only_platform_admins_set_rates(client):
    assert set_rates(client, ZWG="26.80").status_code == 200
    assert client.put("/admin/fx/rates", headers=PHARMACY, json={"rates": {"ZWG": "27"}}).status_code == 403
    assert client.put("/admin/fx/rates", headers=ADMIN, json={"rates": {"ZWG": "0"}}).status_code == 422
    assert client.put("/admin/fx/rates", headers=ADMIN, json={"rates": {"EUR": "1"}}).status_code == 422
    assert client.put("/admin/fx/rates", headers=ADMIN,
                      json={"rates": {"ZWG": "27"}, "effective_date": "2999-01-01"}).status_code == 400
    r = client.get("/fx/rates", headers=PHARMACY).json()
    assert r["rates"] == {"USD": "1", "ZWG": "26.800000"} and r["source"]["ZWG"] == "RBZ interbank"
    assert [h["per_usd"] for h in client.get("/admin/fx/history", headers=ADMIN).json()] == ["26.800000"]


def test_mixed_currency_cart_splits_and_snapshots_rates(client):
    set_rates(client, ZWG="26.80")
    orders = checkout(client, [{"product_id": 1, "quantity": 2}, {"product_id": 4, "quantity": 1}]).json()
    by_cur = {o["currency"]: o for o in orders}
    assert set(by_cur) == {"USD", "ZWG"} and {o["supplier_org_id"] for o in orders} == {10}
    assert by_cur["USD"]["subtotal"] == "25.00" and by_cur["USD"]["amount_usd"] == "25.00"
    assert by_cur["ZWG"]["subtotal"] == "268.00" and by_cur["ZWG"]["amount_usd"] == "10.00"
    assert by_cur["ZWG"]["fx_rates"]["ZWG"] == "26.800000"


def test_budget_counts_every_currency_at_the_checkout_rate(client):
    client.put("/budget", headers=PHARMACY, json={"amount": "1000.00", "currency": "ZWG"})
    checkout(client, [{"product_id": 1, "quantity": 2}])  # USD 25.00 before any rate exists
    b = client.get("/budget", headers=PHARMACY).json()
    assert b["committed"] == "0.00" and b["unconverted_currencies"] == ["USD"]

    set_rates(client, ZWG="26.80")
    b = client.get("/budget", headers=PHARMACY).json()  # old order falls back to today's rate
    assert b["committed"] == "670.00" and b["unconverted_currencies"] == []

    checkout(client, [{"product_id": 1, "quantity": 2}])  # snapshots 26.80
    set_rates(client, ZWG="30.00")  # rate moves after checkout
    b = client.get("/budget", headers=PHARMACY).json()
    assert b["committed"] == "1420.00"  # 25 * 30 (no snapshot) + 25 * 26.80 (snapshot)
    assert round(b["percent_used"]) == 142

    s = client.get("/orders/summary", headers=PHARMACY, params={"currency": "ZWG"}).json()
    assert s["currency"] == "ZWG" and s["month_total"] == "1420.00"
    usd = client.get("/orders/summary", headers=PHARMACY).json()
    assert usd["month_total"] == "50.00"


def test_payments_service_updates_payment_status(client, catalog):
    from tests.conftest import SERVICE
    [o] = checkout(client, [{"product_id": 1, "quantity": 2}]).json()
    assert o["payment_status"] == "UNPAID"
    assert client.get(f"/internal/orders/{o['order_number']}").status_code == 403
    info = client.get(f"/internal/orders/{o['order_number']}", headers=SERVICE).json()
    assert info["subtotal"] == "25.00" and info["pharmacy_org_id"] == 20 and info["supplier_org_id"] == 10
    r = client.post(f"/internal/orders/{o['order_number']}/payment", headers=SERVICE,
                    json={"payment_status": "PAID", "paid_via": "ecocash"})
    assert r.json()["payment_status"] == "PAID"
    d = client.get(f"/orders/{o['id']}", headers=PHARMACY).json()
    assert d["payment_status"] == "PAID" and d["paid_via"] == "ecocash" and d["paid_at"]
    assert client.get("/internal/orders/PO-NOPE", headers=SERVICE).status_code == 404
