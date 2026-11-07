import os

os.environ["DATABASE_URL"] = "sqlite:///./test_identity.db"

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client():
    from app.main import app, db
    from multistock_common.db import Base

    Base.metadata.drop_all(db.engine)
    with TestClient(app) as c:
        yield c
    Base.metadata.drop_all(db.engine)
