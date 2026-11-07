import os
from datetime import timedelta

os.environ["DATABASE_URL"] = "sqlite:///./test_catalog.db"

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


@pytest.fixture()
def client():
    from app.main import app, db
    from multistock_common.db import Base

    Base.metadata.drop_all(db.engine)
    with TestClient(app) as c:
        yield c
    Base.metadata.drop_all(db.engine)
