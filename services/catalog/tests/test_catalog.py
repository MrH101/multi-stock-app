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
    assert client.get("/products", headers=PHARMACY, params={"q": "amoxicillin 500mg"}).json()["total"] == 1
    assert client.get("/products", headers=PHARMACY, params={"q": "amoxicillin 250mg"}).json()["total"] == 0


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


def test_monitoring_snapshot_reports_stock_demand_and_expiry(client):
    pid = make_product(client)
    client.post(f"/products/{pid}/batches", headers=SUPPLIER, json={"batch_number": "SOON", "expiry_date": in_days(20), "quantity": 10})
    client.post(f"/products/{pid}/batches", headers=SUPPLIER, json={"batch_number": "LATE", "expiry_date": in_days(400), "quantity": 30})
    client.post("/internal/reservations", headers=SERVICE, json={"order_ref": "PO-1", "lines": [{"product_id": pid, "quantity": 15}]})
    client.post("/internal/reservations", headers=SERVICE, json={"order_ref": "PO-2", "lines": [{"product_id": pid, "quantity": 5}]})
    client.post("/internal/reservations/PO-2/release", headers=SERVICE)

    assert client.get("/internal/monitoring/inventory").status_code == 403
    snap = client.get("/internal/monitoring/inventory", headers=SERVICE, params={"expiry_days": 90}).json()
    [p] = snap["products"]
    assert p["stock_available"] == 25 and p["demand_units"] == 15 and p["reorder_level"] == 50
    assert snap["batches"] == []  # SOON was used up first (FEFO); LATE is outside the window

    other = make_product(client, name="Panado", generic_name="Paracetamol", sku="PAN")
    client.post(f"/products/{other}/batches", headers=SUPPLIER, json={"batch_number": "P1", "expiry_date": in_days(20), "quantity": 8})
    [b] = client.get("/internal/monitoring/inventory", headers=SERVICE).json()["batches"]
    assert b["batch_number"] == "P1" and b["quantity_available"] == 8 and b["supplier_org_id"] == 10


def test_mcaz_category_and_registration_number(client):
    # old category names are still accepted and mapped to the MCAZ ones
    pid = make_product(client, schedule="PRESCRIPTION", mcaz_registration_number="  2009/7.3/4567 ")
    p = client.get(f"/products/{pid}", headers=PHARMACY).json()
    assert p["schedule"] == "PP" and p["mcaz_registration_number"] == "2009/7.3/4567"
    make_product(client, name="Panado", generic_name="Paracetamol", sku="PAN", schedule="HR")
    assert client.post("/products", headers=SUPPLIER, json={**AMOX, "sku": "X", "schedule": "BOGUS"}).status_code == 422

    assert client.get("/products", headers=PHARMACY, params={"q": "2009/7.3"}).json()["total"] == 1
    only_pp = client.get("/products", headers=PHARMACY, params={"schedule": ["PP", "CD"]}).json()
    assert [x["name"] for x in only_pp["items"]] == ["Amoxil"]

    client.post(f"/products/{pid}/batches", headers=SUPPLIER, json={"batch_number": "B1", "expiry_date": in_days(300), "quantity": 5})
    r = client.post("/internal/reservations", headers=SERVICE, json={"order_ref": "PO-9", "lines": [{"product_id": pid, "quantity": 2}]})
    line = r.json()["lines"][0]
    assert line["schedule"] == "PP" and line["mcaz_registration_number"] == "2009/7.3/4567"


def test_existing_databases_are_upgraded(client):
    from sqlalchemy import text
    from app.main import db, upgrade_schema

    pid = make_product(client)
    with db.engine.begin() as c:  # a row written before the MCAZ categories existed
        c.execute(text("UPDATE products SET schedule = 'CONTROLLED' WHERE id = :id"), {"id": pid})
        c.execute(text("CREATE TABLE legacy_t (id INTEGER PRIMARY KEY)"))
    upgrade_schema()
    assert client.get(f"/products/{pid}", headers=PHARMACY).json()["schedule"] == "CD"
    assert db.ensure_columns("legacy_t", {"note": "VARCHAR(10)"}) == ["note"]
    assert db.ensure_columns("legacy_t", {"note": "VARCHAR(10)"}) == []  # idempotent
    with db.engine.begin() as c:
        c.execute(text("DROP TABLE legacy_t"))
