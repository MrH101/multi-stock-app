from datetime import datetime, timedelta, timezone

from app import rules
from app.config import Settings
from app.models import Severity

from .conftest import FakeSources

CFG = Settings()


def by_key(findings):
    return {(f.org_id, f.key): f for f in findings}


def test_stock_levels_flag_stockouts_and_short_cover():
    inv = FakeSources().inventory(90, 30)
    found = by_key(rules.stock_levels(inv, CFG))
    out = found[(10, "stock:1")]
    assert out.kind == "out_of_stock" and out.severity == Severity.CRITICAL
    assert "Suggested replenishment: about 80 units" in out.body  # 2/day * 30 + 20 reorder - 0
    cover = found[(10, "stock:2")]
    assert cover.kind == "low_cover" and cover.severity == Severity.CRITICAL
    assert cover.metrics["days_of_cover"] == 5.0
    assert (11, "stock:3") not in found  # healthy product stays quiet


def test_reorder_level_without_demand():
    inv = {"demand_days": 30, "products": [{"id": 9, "supplier_org_id": 10, "supplier_name": "S", "name": "Ventolin",
                                            "reorder_level": 10, "stock_available": 6, "demand_units": 0}]}
    [f] = rules.stock_levels(inv, CFG)
    assert f.kind == "below_reorder" and f.severity == Severity.WARNING


def test_expiry_flags_expired_and_unsellable_stock():
    inv = FakeSources().inventory(90, 30)
    found = by_key(rules.expiry(inv, CFG))
    expired = found[(10, "expiry:100")]
    assert expired.kind == "expired_on_hand" and expired.severity == Severity.CRITICAL
    soon = found[(11, "expiry:101")]
    assert soon.severity == Severity.CRITICAL  # 20 days <= 30
    # demand is 1/day, so ~20 of 200 sell before expiry
    assert soon.metrics["units_at_risk"] == 180 and "will not sell in time" in soon.body


def test_order_sla_notifies_both_sides():
    snap = FakeSources().snapshot
    found = by_key(rules.order_sla(snap, CFG))
    assert found[(10, "order:7:review")].severity == Severity.WARNING
    assert found[(20, "order:7:awaiting")].severity == Severity.INFO
    later = datetime.now(timezone.utc) + timedelta(hours=24)
    assert by_key(rules.order_sla(snap, CFG, now=later))[(10, "order:7:review")].severity == Severity.CRITICAL


def test_budget_levels_and_projection():
    def run(committed, day):
        snap = {"budgets": [{"pharmacy_org_id": 20, "period": "2026-11-01", "amount": "1000", "currency": "USD",
                             "committed": committed, "days_elapsed": day, "days_in_month": 30}]}
        return rules.budgets(snap, CFG)

    assert run("1250", 10)[0].kind == "budget_exceeded"
    assert run("850", 25)[0].kind == "budget_high"
    projected = run("400", 10)[0]  # 40/day -> 1200 by month end
    assert projected.kind == "budget_projection" and "USD 1,200.00" in projected.body
    assert run("100", 25) == []
    assert run("400", 3) == []  # too early in the month to project


def test_supply_watch_suggests_in_stock_alternative():
    src = FakeSources()
    [f] = rules.supply_watch(src.snapshot, src.inventory(90, 30))
    assert f.org_id == 20 and f.kind == "regular_item_unavailable"
    assert "Amoxicillin Generic from Other Wholesale" in f.body
    assert f.metrics["alternatives"] == [3]


def test_platform_health():
    found = rules.platform_health(1, {"orders": {"up": False, "detail": "ConnectError"},
                                      "catalog": {"up": True}}, ["catalog: HTTP 500 on /x"], True, "HTTP 402: no balance")
    kinds = {f.kind for f in found}
    assert kinds == {"service_down", "monitoring_source_failed", "llm_unavailable"}
    assert rules.platform_health(None, {"orders": {"up": False}}, [], False, None) == []
