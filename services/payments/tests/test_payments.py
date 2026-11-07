from datetime import datetime, timedelta, timezone

from app import main
from app.models import MerchantAccount, Payment
from app.service import safe_poll_url

from .conftest import KEY, OTHER_PHARMACY, OTHER_SUPPLIER, PHARMACY, SUPPLIER, SUPPLIER_STAFF

PDF = b"%PDF-1.4\n% bank confirmation\n"


def connect_paynow(client, **extra):
    body = {"paynow_enabled": True, "paynow_integration_id": "21436", "paynow_integration_key": KEY,
            "bank_name": "CBZ", "bank_account_name": "Pharma Wholesale", "bank_account_number": "01234567890", **extra}
    r = client.put("/merchant-accounts/ZWG", headers=SUPPLIER, json=body)
    assert r.status_code == 200, r.text
    return r.json()


def pay(client, method="ecocash", phone="+263 77 123 4567"):
    return client.post("/payments", headers=PHARMACY, json={"order_number": "PO-1", "method": method, "phone": phone})


def published(kind):
    return [e for e in main.events.published if e["type"] == kind]


def test_supplier_connects_paynow_and_the_key_is_protected(client):
    assert client.put("/merchant-accounts/ZWG", headers=SUPPLIER_STAFF, json={}).status_code == 403
    assert client.put("/merchant-accounts/ZWG", headers=SUPPLIER, json={"paynow_enabled": True}).status_code == 422
    out = connect_paynow(client)
    assert out["paynow_integration_key_masked"].endswith(KEY[-4:]) and KEY not in str(out)
    with main.db.SessionLocal() as s:
        stored = s.query(MerchantAccount).one().paynow_integration_key_enc
    assert KEY not in stored  # encrypted at rest
    # updating other fields keeps the key
    client.put("/merchant-accounts/ZWG", headers=SUPPLIER, json={"paynow_enabled": True, "paynow_integration_id": "21436",
                                                                "bank_branch": "Samora"})
    usd, zwg = client.get("/merchant-accounts", headers=SUPPLIER).json()[:2]
    assert usd["currency"] == "USD" and usd["paynow_enabled"] is False
    assert zwg["paynow_integration_key_masked"] and zwg["bank_branch"] == "Samora"


def test_payment_options(client):
    o = client.get("/orders/PO-1/options", headers=PHARMACY).json()
    assert o["methods"] == [] and "hasn't set up online payments" in o["reason"]
    connect_paynow(client)
    o = client.get("/orders/PO-1/options", headers=PHARMACY).json()
    assert o["methods"] == ["ecocash", "onemoney", "innbucks", "paynow_web", "bank_transfer"]
    assert o["amount"] == "536.00" and o["bank"]["bank_account_number"] == "01234567890"
    assert client.get("/orders/PO-1/options", headers=OTHER_PHARMACY).status_code == 404


def test_ecocash_express_checkout_and_signed_callback(client, orders, paynow_server):
    connect_paynow(client)
    r = pay(client)
    assert r.status_code == 201, r.text
    p = r.json()
    assert p["status"] == "PENDING" and p["phone"] == "0771234567" and "*151#" in p["instructions"]
    sent = dict(paynow_server.requests[0])
    assert [k for k, _ in paynow_server.requests[0]] == ["resulturl", "returnurl", "reference", "amount", "id",
                                                         "additionalinfo", "authemail", "phone", "method", "status", "hash"]
    assert sent["amount"] == "536.00" and sent["id"] == "21436" and sent["method"] == "ecocash"
    assert sent["resulturl"].endswith(f"/api/payments/paynow/result/{p['reference']}")
    assert orders.updates[-1] == ("PO-1", "PENDING", "ecocash")
    assert pay(client).status_code == 409  # no double charge while one is in progress

    bad = paynow_server.callback_body(p["reference"], key="wrong-key")
    assert client.post(f"/paynow/result/{p['reference']}", content=bad,
                       headers={"Content-Type": "application/x-www-form-urlencoded"}).status_code == 403
    assert client.get("/payments", headers=PHARMACY, params={"order_number": "PO-1"}).json()[0]["status"] == "PENDING"

    good = paynow_server.callback_body(p["reference"])
    for _ in range(2):  # Paynow may repeat the callback
        r = client.post(f"/paynow/result/{p['reference']}", content=good,
                        headers={"Content-Type": "application/x-www-form-urlencoded"})
        assert r.status_code == 200 and r.text == "OK"
    [done] = client.get("/payments", headers=SUPPLIER, params={"order_number": "PO-1"}).json()
    assert done["status"] == "PAID" and done["provider_reference"] == "PN-991" and done["paid_at"]
    assert orders.updates[-1] == ("PO-1", "PAID", "ecocash") and len(published("payment.paid")) == 1
    assert client.get("/orders/PO-1/options", headers=PHARMACY).json()["reason"] == "This order is paid."
    assert pay(client).status_code == 409


def test_amount_mismatch_is_disputed_not_paid(client, orders, paynow_server):
    connect_paynow(client)
    ref = pay(client).json()["reference"]
    body = paynow_server.callback_body(ref, amount="5.36")
    client.post(f"/paynow/result/{ref}", content=body, headers={"Content-Type": "application/x-www-form-urlencoded"})
    [p] = client.get("/payments", headers=PHARMACY, params={"order_number": "PO-1"}).json()
    assert p["status"] == "DISPUTED" and "expected 536.00" in p["error"]
    assert orders.orders["PO-1"]["payment_status"] != "PAID"


def test_polling_settles_when_callbacks_are_lost(client, orders, paynow_server):
    connect_paynow(client)
    p = pay(client, method="onemoney", phone="0712345678").json()
    assert client.post(f"/payments/{p['id']}/refresh", headers=PHARMACY).json()["status"] == "PENDING"
    paynow_server.status = "Paid"
    assert main.poll_pending() == 1
    assert client.get("/payments", headers=PHARMACY, params={"order_number": "PO-1"}).json()[0]["status"] == "PAID"


def test_cancelled_and_expired_payments(client, orders, paynow_server):
    connect_paynow(client)
    p = pay(client).json()
    paynow_server.status = "Cancelled"
    assert client.post(f"/payments/{p['id']}/refresh", headers=PHARMACY).json()["status"] == "CANCELLED"
    assert orders.updates[-1][1] == "UNPAID" and published("payment.cancelled")

    p2 = pay(client).json()  # may retry after a cancelled attempt
    paynow_server.status = "Sent"
    with main.db.SessionLocal() as s:
        s.get(Payment, p2["id"]).created_at = datetime.now(timezone.utc) - timedelta(hours=25)
        s.commit()
    main.poll_pending()
    assert client.get("/payments", headers=PHARMACY, params={"order_number": "PO-1"}).json()[0]["status"] == "FAILED"


def test_web_checkout_innbucks_and_provider_errors(client, paynow_server):
    connect_paynow(client)
    web = pay(client, method="paynow_web", phone=None).json()
    assert web["redirect_url"].startswith("https://www.paynow.co.zw/payment/confirm/")
    assert "phone" not in dict(paynow_server.requests[-1])
    paynow_server.status = "Cancelled"
    client.post(f"/payments/{web['id']}/refresh", headers=PHARMACY)

    inn = pay(client, method="innbucks", phone="0771234567").json()
    assert inn["innbucks_code"] == "123456789" and inn["innbucks_expires"]
    paynow_server.status = "Cancelled"
    client.post(f"/payments/{inn['id']}/refresh", headers=PHARMACY)

    paynow_server.fail_with = "Invalid Id."
    r = pay(client)
    assert r.status_code == 502 and "Invalid Id" in r.json()["detail"]
    assert client.get("/payments", headers=PHARMACY, params={"order_number": "PO-1"}).json()[0]["status"] == "FAILED"
    assert pay(client, phone="0123").status_code == 422


def test_proof_of_payment_flow(client, orders):
    connect_paynow(client)
    files = {"file": ("transfer.pdf", PDF, "application/pdf")}
    assert client.post("/payments/proof", headers=PHARMACY, data={"order_number": "PO-1"},
                       files={"file": ("x.exe", b"MZ\x90", "application/octet-stream")}).status_code == 422
    r = client.post("/payments/proof", headers=PHARMACY, data={"order_number": "PO-1", "bank_reference": "FT2611"},
                    files=files)
    assert r.status_code == 201, r.text
    p = r.json()
    assert p["status"] == "AWAITING_CONFIRMATION" and p["proofs"][0]["bank_reference"] == "FT2611"
    assert orders.updates[-1] == ("PO-1", "AWAITING_CONFIRMATION", "bank_transfer")
    proof_url = f"/payments/{p['id']}/proofs/{p['proofs'][0]['id']}"
    assert client.get(proof_url, headers=SUPPLIER).content == PDF
    assert client.get(proof_url, headers=OTHER_SUPPLIER).status_code == 404

    assert client.post(f"/payments/{p['id']}/review", headers=SUPPLIER, json={"accept": False}).status_code == 422
    assert client.post(f"/payments/{p['id']}/review", headers=PHARMACY, json={"accept": True}).status_code == 403
    r = client.post(f"/payments/{p['id']}/review", headers=SUPPLIER, json={"accept": False, "note": "Not in our account"})
    assert r.json()["status"] == "REJECTED" and published("payment.rejected")

    p2 = client.post("/payments/proof", headers=PHARMACY, data={"order_number": "PO-1"},
                     files={"file": ("pop.png", b"\x89PNG\r\n\x1a\n...", "image/png")}).json()
    assert p2["id"] != p["id"]
    ok = client.post(f"/payments/{p2['id']}/review", headers=SUPPLIER, json={"accept": True}).json()
    assert ok["status"] == "PAID" and orders.updates[-1] == ("PO-1", "PAID", "bank_transfer")


def test_cannot_pay_unpayable_orders(client, orders):
    connect_paynow(client)
    orders.orders["PO-1"]["status"] = "CANCELLED"
    assert pay(client).status_code == 409
    assert "cancelled" in client.get("/orders/PO-1/options", headers=PHARMACY).json()["reason"]
    assert client.post("/payments", headers=SUPPLIER, json={"order_number": "PO-1", "method": "ecocash"}).status_code == 403


def test_poll_urls_must_point_at_paynow():
    base = "https://www.paynow.co.zw"
    assert safe_poll_url("https://www.paynow.co.zw/interface/poll?guid=1", base)
    assert safe_poll_url("https://evil.example/poll", base) is None
    assert safe_poll_url("http://www.paynow.co.zw/interface/poll", base) is None
