from datetime import date, timedelta

from tests.conftest import OTHER_SUPPLIER, PHARMACY, SERVICE, SUPPLIER

AMOX = {"name": "Amoxil", "generic_name": "Amoxicillin", "strength": "500mg", "dosage_form": "CAPSULE",
        "pack_size": "100s", "unit_price": "12.50", "reorder_level": 50}


def in_days(n):
    return (date.today() + timedelta(days=n)).isoformat()


def make_product(client, **extra):
    r = client.post("/products", headers=SUPPLIER, json={**AMOX, **extra})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_only_suppliers_manage_their_own_products(client):
    assert client.post("/products", headers=PHARMACY, json=AMOX).status_code == 403
    pid = make_product(client)
    assert client.patch(f"/products/{pid}", headers=OTHER_SUPPLIER, json={"unit_price": "1.00"}).status_code == 404
    assert client.post(f"/products/{pid}/batches", headers=OTHER_SUPPLIER,
                       json={"batch_number": "X", "expiry_date": in_days(100), "quantity": 5}).status_code == 404


def test_search_shows_sellable_stock_and_nearest_expiry(client):
    pid = make_product(client)
    make_product(client, name="Panado", generic_name="Paracetamol", dosage_form="TABLET")
    client.post(f"/products/{pid}/batches", headers=SUPPLIER, json={"batch_number": "B2", "expiry_date": in_days(400), "quantity": 30})
    client.post(f"/products/{pid}/batches", headers=SUPPLIER, json={"batch_number": "B1", "expiry_date": in_days(60), "quantity": 20})

    r = client.get("/products", headers=PHARMACY, params={"q": "amoxicillin"}).json()
    assert r["total"] == 1
    item = r["items"][0]
    assert item["stock_available"] == 50
    assert item["nearest_expiry"] == in_days(60)
    assert item["supplier_name"] == "Pharma Wholesale"
    assert client.get("/products", headers=PHARMACY, params={"in_stock": True}).json()["total"] == 1


def test_fefo_reservation_release_and_commit(client):
    pid = make_product(client)
    client.post(f"/products/{pid}/batches", headers=SUPPLIER, json={"batch_number": "LATE", "expiry_date": in_days(400), "quantity": 30})
    client.post(f"/products/{pid}/batches", headers=SUPPLIER, json={"batch_number": "SOON", "expiry_date": in_days(60), "quantity": 20})

    # internal endpoints refuse user tokens
    assert client.post("/internal/reservations", headers=PHARMACY,
                       json={"order_ref": "PO-1", "lines": [{"product_id": pid, "quantity": 1}]}).status_code == 403

    r = client.post("/internal/reservations", headers=SERVICE,
                    json={"order_ref": "PO-1", "lines": [{"product_id": pid, "quantity": 25}]})
    assert r.status_code == 200, r.text
    allocations = r.json()["lines"][0]["allocations"]
    assert [(a["batch_number"], a["quantity"]) for a in allocations] == [("SOON", 20), ("LATE", 5)]
    assert r.json()["lines"][0]["unit_price"] == "12.50"

    # idempotent retry does not double-reserve
    again = client.post("/internal/reservations", headers=SERVICE,
                        json={"order_ref": "PO-1", "lines": [{"product_id": pid, "quantity": 25}]})
    assert again.json()["lines"][0]["quantity"] == 25
    assert client.get(f"/products/{pid}", headers=PHARMACY).json()["stock_available"] == 25

    # overselling is rejected atomically
    r = client.post("/internal/reservations", headers=SERVICE,
                    json={"order_ref": "PO-2", "lines": [{"product_id": pid, "quantity": 26}]})
    assert r.status_code == 409
    assert client.get(f"/products/{pid}", headers=PHARMACY).json()["stock_available"] == 25

    assert client.post("/internal/reservations/PO-1/release", headers=SERVICE).json() == {"released": 2}
    assert client.get(f"/products/{pid}", headers=PHARMACY).json()["stock_available"] == 50

    client.post("/internal/reservations", headers=SERVICE,
                json={"order_ref": "PO-3", "lines": [{"product_id": pid, "quantity": 10}]})
    assert client.post("/internal/reservations/PO-3/commit", headers=SERVICE).json() == {"committed": 1}
    batches = client.get(f"/products/{pid}/batches", headers=SUPPLIER).json()
    soon = next(b for b in batches if b["batch_number"] == "SOON")
    assert soon["quantity_available"] == 10 and soon["quantity_reserved"] == 0


def test_adjustments_are_audited_and_alerts(client):
    pid = make_product(client)
    batch = client.post(f"/products/{pid}/batches", headers=SUPPLIER,
                        json={"batch_number": "B1", "expiry_date": in_days(30), "quantity": 40}).json()
    assert client.post(f"/batches/{batch['id']}/adjustments", headers=SUPPLIER,
                       json={"change": -100, "reason": "DAMAGED"}).status_code == 400
    client.post(f"/batches/{batch['id']}/adjustments", headers=SUPPLIER, json={"change": -5, "reason": "DAMAGED", "note": "broken"})
    moves = client.get(f"/batches/{batch['id']}/movements", headers=SUPPLIER).json()
    assert [m["reason"] for m in moves] == ["DAMAGED", "RECEIVED"]

    alerts = client.get("/inventory/alerts", headers=SUPPLIER).json()
    assert alerts["expiring"][0]["days_to_expiry"] == 30
    assert alerts["low_stock"][0]["stock_available"] == 35
