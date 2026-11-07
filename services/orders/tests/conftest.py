import os
from datetime import timedelta

os.environ["DATABASE_URL"] = "sqlite:///./test_orders.db"

import pytest
from fastapi.testclient import TestClient

from multistock_common.auth import encode_token

SECRET = "dev-only-change-me-dev-only-change-me"


def token(user_id: int, org_id: int, org_type: str, org_name: str = "Org", role: str = "OWNER") -> dict:
    t = encode_token({"sub": str(user_id), "org_id": org_id, "org_type": org_type, "org_name": org_name,
                      "role": role, "name": "Test", "email": "t@t.co.zw"}, SECRET, "HS256",
                     timedelta(minutes=5), "access")
    return {"Authorization": f"Bearer {t}"}


SUPPLIER = token(1, 10, "SUPPLIER", "Pharma Wholesale")
OTHER_SUPPLIER = token(2, 11, "SUPPLIER", "Other Wholesale")
PHARMACY = token(3, 20, "PHARMACY", "Avenues Pharmacy")
SERVICE = {"X-Service-Token": "dev-service-token"}


class FakeCatalog:
    """In-memory stand-in for the catalog service's internal API."""

    def __init__(self):
        self.stock = {
            1: {"id": 1, "name": "Amoxil 500mg", "supplier_org_id": 10, "supplier_name": "Pharma Wholesale",
                "unit_price": "12.50", "currency": "USD", "is_active": True, "qty": 100},
            2: {"id": 2, "name": "Panado", "supplier_org_id": 10, "supplier_name": "Pharma Wholesale",
                "unit_price": "2.00", "currency": "USD", "is_active": True, "qty": 100},
            3: {"id": 3, "name": "Insulin Pen", "supplier_org_id": 11, "supplier_name": "Other Wholesale",
                "unit_price": "30.00", "currency": "USD", "is_active": True, "qty": 5},
        }
        self.reserved: dict[str, list[dict]] = {}
        self.calls: list[tuple[str, str]] = []

    def products(self, ids):
        return [{k: v for k, v in self.stock[i].items() if k != "qty"} for i in ids if i in self.stock]

    def reserve(self, ref, lines):
        from fastapi import HTTPException
        for l in lines:
            if self.stock[l["product_id"]]["qty"] < l["quantity"]:
                raise HTTPException(409, {"message": "Some items cannot be fulfilled", "problems": ["short"]})
        for l in lines:
            self.stock[l["product_id"]]["qty"] -= l["quantity"]
        self.reserved[ref] = lines
        self.calls.append(("reserve", ref))
        out = []
        for l in lines:
            p = self.stock[l["product_id"]]
            out.append({"product_id": p["id"], "product_name": p["name"], "generic_name": None, "strength": None,
                        "pack_size": None, "supplier_org_id": p["supplier_org_id"], "supplier_name": p["supplier_name"],
                        "unit_price": p["unit_price"], "currency": "USD", "quantity": l["quantity"],
                        "allocations": [{"batch_number": "B1", "expiry_date": "2030-01-01", "quantity": l["quantity"]}]})
        return out

    def release(self, ref):
        self.calls.append(("release", ref))
        for l in self.reserved.pop(ref, []):
            self.stock[l["product_id"]]["qty"] += l["quantity"]

    def commit(self, ref):
        self.calls.append(("commit", ref))
        self.reserved.pop(ref, None)


@pytest.fixture()
def catalog():
    return FakeCatalog()


@pytest.fixture()
def client(catalog):
    from app.catalog_client import get_catalog
    from app.main import app, db
    from multistock_common.db import Base

    Base.metadata.drop_all(db.engine)
    app.dependency_overrides[get_catalog] = lambda: catalog
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    Base.metadata.drop_all(db.engine)
