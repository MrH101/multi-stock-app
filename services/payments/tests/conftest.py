import os
import shutil
from datetime import timedelta
from urllib.parse import parse_qsl, urlencode

os.environ["DATABASE_URL"] = "sqlite:///./test_payments.db"
os.environ["UPLOAD_DIR"] = "./test_uploads"
os.environ["POLL_INTERVAL_SECONDS"] = "0"
os.environ["PAYNOW_BASE_URL"] = "https://www.paynow.co.zw"

import httpx
import pytest
from fastapi.testclient import TestClient

from multistock_common.auth import encode_token

SECRET = "dev-only-change-me-dev-only-change-me"
KEY = "3e9fed89-60e1-4ce5-ab6e-6b1eb2d4f977"


def token(user_id, org_id, org_type, org_name="Org", role="OWNER", email="t@avenues.co.zw"):
    t = encode_token({"sub": str(user_id), "org_id": org_id, "org_type": org_type, "org_name": org_name,
                      "role": role, "name": "Test User", "email": email}, SECRET, "HS256",
                     timedelta(minutes=5), "access")
    return {"Authorization": f"Bearer {t}"}


SUPPLIER = token(1, 10, "SUPPLIER", "Pharma Wholesale")
SUPPLIER_STAFF = token(5, 10, "SUPPLIER", "Pharma Wholesale", role="STAFF")
OTHER_SUPPLIER = token(2, 11, "SUPPLIER", "Other Wholesale")
PHARMACY = token(3, 20, "PHARMACY", "Avenues Pharmacy")
OTHER_PHARMACY = token(4, 21, "PHARMACY", "Other Pharmacy")


class FakeOrders:
    def __init__(self):
        self.orders = {
            "PO-1": {"id": 7, "order_number": "PO-1", "status": "ACCEPTED", "pharmacy_org_id": 20,
                     "pharmacy_name": "Avenues Pharmacy", "supplier_org_id": 10, "supplier_name": "Pharma Wholesale",
                     "subtotal": "536.00", "currency": "ZWG", "payment_method": "MOBILE_MONEY",
                     "payment_status": "UNPAID", "created_by_user_id": 3},
        }
        self.updates: list[tuple[str, str, str | None]] = []

    def get(self, number):
        from fastapi import HTTPException
        if number not in self.orders:
            raise HTTPException(404, "Order not found")
        return dict(self.orders[number])

    def set_payment(self, number, status, via, paid_at):
        self.updates.append((number, status, via))
        self.orders[number]["payment_status"] = status


class FakePaynowServer:
    """Speaks Paynow's protocol: checks our hash, answers with signed url-encoded bodies."""

    def __init__(self):
        from app.paynow import make_hash
        self.make_hash = make_hash
        self.requests: list[list[tuple[str, str]]] = []
        self.status = "Sent"
        self.amount = None
        self.fail_with = None
        self.reference = None

    def signed(self, values):
        return urlencode([*values, ("hash", self.make_hash(values, KEY))])

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/interface/poll"):
            ref = self.reference
            values = [("reference", ref), ("amount", self.amount or "536.00"), ("paynowreference", "PN-991"),
                      ("pollurl", str(request.url)), ("status", self.status)]
            return httpx.Response(200, text=self.signed(values))
        fields = parse_qsl(request.content.decode())
        self.requests.append(fields)
        sent = dict(fields)
        assert sent["hash"] == self.make_hash(fields, KEY), "client hash wrong"
        if self.fail_with:
            return httpx.Response(200, text=urlencode([("status", "Error"), ("error", self.fail_with)]))
        self.reference = sent["reference"]
        poll = f"https://www.paynow.co.zw/interface/poll?guid={sent['reference']}"
        if request.url.path.endswith("remotetransaction"):
            values = [("status", "Ok"), ("instructions", "Dial *151# and approve the payment"), ("pollurl", poll)]
            if sent.get("method") == "innbucks":
                values += [("authorizationcode", "123456789"), ("authorizationexpires", "2026-11-07 22:00")]
        else:
            values = [("status", "Ok"), ("browserurl", f"https://www.paynow.co.zw/payment/confirm/{sent['reference']}"),
                      ("pollurl", poll)]
        return httpx.Response(200, text=self.signed(values))

    def callback_body(self, reference, status="Paid", amount="536.00", key=KEY):
        values = [("reference", reference), ("amount", amount), ("paynowreference", "PN-991"),
                  ("pollurl", f"https://www.paynow.co.zw/interface/poll?guid={reference}"), ("status", status)]
        return urlencode([*values, ("hash", self.make_hash(values, key))])


@pytest.fixture()
def orders():
    return FakeOrders()


@pytest.fixture()
def paynow_server():
    return FakePaynowServer()


@pytest.fixture()
def client(orders, paynow_server):
    from app import main
    from app.paynow import PaynowClient
    from multistock_common.db import Base

    Base.metadata.drop_all(main.db.engine)
    shutil.rmtree("./test_uploads", ignore_errors=True)
    fake_paynow = PaynowClient("https://www.paynow.co.zw", transport=httpx.MockTransport(paynow_server.handler))
    main.app.dependency_overrides[main.get_orders] = lambda: orders
    main.app.dependency_overrides[main.get_paynow] = lambda: fake_paynow
    main._orders, main._paynow = orders, fake_paynow  # used by the callback and the poller
    main.events.published.clear()
    with TestClient(main.app) as c:
        yield c
    main.app.dependency_overrides.clear()
    Base.metadata.drop_all(main.db.engine)
    shutil.rmtree("./test_uploads", ignore_errors=True)
