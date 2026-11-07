import os
from datetime import date, datetime, timedelta, timezone

os.environ["DATABASE_URL"] = "sqlite:///./test_agent.db"
os.environ["MONITOR_ENABLED"] = "false"
os.environ["CAIMEX_API_KEY"] = ""

import pytest
from fastapi.testclient import TestClient

from multistock_common.auth import encode_token

SECRET = "dev-only-change-me-dev-only-change-me"


def token(user_id: int, org_id: int, org_type: str, org_name: str = "Org", role: str = "OWNER") -> dict:
    t = encode_token({"sub": str(user_id), "org_id": org_id, "org_type": org_type, "org_name": org_name,
                      "role": role, "name": "Test User", "email": "t@t.co.zw"}, SECRET, "HS256",
                     timedelta(minutes=5), "access")
    return {"Authorization": f"Bearer {t}"}


ADMIN = token(99, 1, "PLATFORM", "Multi-Stock Platform")
SUPPLIER = token(1, 10, "SUPPLIER", "Pharma Wholesale")
OTHER_SUPPLIER = token(2, 11, "SUPPLIER", "Other Wholesale")
PHARMACY = token(3, 20, "PHARMACY", "Avenues Pharmacy")
SERVICE = {"X-Service-Token": "dev-service-token"}

TODAY = date.today()


def iso(d) -> str:
    return d.isoformat()


class FakeSources:
    """Snapshot shapes match the catalog / orders / identity internal endpoints."""

    def __init__(self):
        self.fail: set[str] = set()
        self.down: set[str] = set()
        self.orgs = [
            {"id": 1, "name": "Multi-Stock Platform", "type": "PLATFORM", "is_active": True, "verified": True},
            {"id": 10, "name": "Pharma Wholesale", "type": "SUPPLIER", "is_active": True, "verified": True},
            {"id": 11, "name": "Other Wholesale", "type": "SUPPLIER", "is_active": True, "verified": True},
            {"id": 20, "name": "Avenues Pharmacy", "type": "PHARMACY", "is_active": True, "verified": True},
        ]
        self.products = [
            # out of stock with demand
            {"id": 1, "supplier_org_id": 10, "supplier_name": "Pharma Wholesale", "name": "Amoxil", "strength": "500mg",
             "generic_name": "Amoxicillin", "reorder_level": 20, "unit_price": "12.50", "currency": "USD",
             "stock_available": 0, "nearest_expiry": None, "demand_units": 60},
            # 5 days of cover: 50 units at 10/day
            {"id": 2, "supplier_org_id": 10, "supplier_name": "Pharma Wholesale", "name": "Panado", "strength": "500mg",
             "generic_name": "Paracetamol", "reorder_level": 0, "unit_price": "2.00", "currency": "USD",
             "stock_available": 50, "nearest_expiry": iso(TODAY + timedelta(days=300)), "demand_units": 300},
            # healthy
            {"id": 3, "supplier_org_id": 11, "supplier_name": "Other Wholesale", "name": "Amoxicillin Generic",
             "strength": "500mg", "generic_name": "Amoxicillin", "reorder_level": 10, "unit_price": "8.00",
             "currency": "USD", "stock_available": 500, "nearest_expiry": iso(TODAY + timedelta(days=400)),
             "demand_units": 30},
        ]
        self.batches = [
            {"batch_id": 100, "product_id": 2, "supplier_org_id": 10, "product_name": "Panado", "batch_number": "PAN-1",
             "expiry_date": iso(TODAY - timedelta(days=3)), "quantity_available": 40, "value": "80.00", "currency": "USD"},
            {"batch_id": 101, "product_id": 3, "supplier_org_id": 11, "product_name": "Amoxicillin Generic",
             "batch_number": "AG-7", "expiry_date": iso(TODAY + timedelta(days=20)), "quantity_available": 200,
             "value": "1600.00", "currency": "USD"},
        ]
        now = datetime.now(timezone.utc)
        self.snapshot = {
            "as_of": iso(TODAY), "demand_days": 90,
            "budgets": [{"pharmacy_org_id": 20, "period": iso(TODAY.replace(day=1)), "amount": "1000.00",
                         "currency": "USD", "committed": "1250.00", "remaining": "-250.00", "is_set": True,
                         "percent_used": 125.0, "days_elapsed": 10, "days_in_month": 30}],
            "open_orders": [{"id": 7, "order_number": "PO-1", "status": "SUBMITTED", "pharmacy_org_id": 20,
                             "pharmacy_name": "Avenues Pharmacy", "supplier_org_id": 10,
                             "supplier_name": "Pharma Wholesale", "subtotal": "250.00", "currency": "USD",
                             "created_at": (now - timedelta(hours=30)).isoformat(),
                             "status_since": (now - timedelta(hours=30)).isoformat()}],
            "demand": [{"pharmacy_org_id": 20, "supplier_org_id": 10, "product_id": 1, "product_name": "Amoxil",
                        "quantity": 40, "order_count": 4}],
        }

    def _check(self, name):
        from app.sources import SourceError
        if name in self.fail:
            raise SourceError(name, "unreachable (ConnectError)")

    def organizations(self):
        self._check("identity")
        return self.orgs

    def inventory(self, expiry_days, demand_days):
        self._check("catalog")
        return {"as_of": iso(TODAY), "demand_days": 30, "products": self.products, "batches": self.batches}

    def orders_snapshot(self, demand_days):
        self._check("orders")
        return self.snapshot

    def health(self):
        return {n: {"up": n not in self.down, "latency_ms": 1.0, "detail": None if n not in self.down else "ConnectError"}
                for n in ("identity", "catalog", "orders", "notifications")}


class FakeLLM:
    """Scripted stand-in for CaimexClient."""

    def __init__(self, replies=None, enabled=True):
        from app.llm import LLMStats
        self.enabled = enabled
        self.model = "fake-model"
        self.fallback_models = []
        self.stats = LLMStats()
        self.replies = list(replies or [])
        self.calls: list[dict] = []

    def chat(self, messages, **kwargs):
        from app.llm import Completion, LLMUnavailable
        self.calls.append({"messages": [dict(m) for m in messages], **kwargs})
        if not self.replies:
            raise LLMUnavailable("no scripted reply")
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return Completion(reply, "fake-model", 0.0001)

    def chat_json(self, messages, **kwargs):
        from app.llm import parse_json
        c = self.chat(messages, json_mode=True, **kwargs)
        return parse_json(c.text), c


@pytest.fixture()
def sources():
    return FakeSources()


@pytest.fixture()
def client(sources):
    from app import main
    from multistock_common.db import Base

    Base.metadata.drop_all(main.db.engine)
    original = (main.monitor.sources, main.monitor.llm, main.assistant.llm, main.llm)
    main.monitor.sources = sources
    main.monitor.llm = FakeLLM(enabled=False)
    main.events.published.clear()
    with TestClient(main.app) as c:
        yield c
    main.monitor.sources, main.monitor.llm, main.assistant.llm, main.llm = original
    Base.metadata.drop_all(main.db.engine)
