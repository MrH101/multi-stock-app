import json
from datetime import datetime, timedelta, timezone

from app import main
from app.llm import LLMUnavailable

from .conftest import ADMIN, OTHER_SUPPLIER, PHARMACY, SERVICE, SUPPLIER, FakeLLM


def alerts_published():
    return [e for e in main.events.published if e["type"] == "agent.alert"]


def run(client):
    r = client.post("/internal/run", headers=SERVICE)
    assert r.status_code == 200, r.text
    return r.json()


def test_run_raises_alerts_and_notifies_each_org(client):
    result = run(client)
    assert result["status"] == "OK" and result["opened"] >= 6

    sup = client.get("/alerts", headers=SUPPLIER).json()
    keys = {a["kind"] for a in sup}
    assert {"out_of_stock", "low_cover", "expired_on_hand", "order_review_overdue"} <= keys
    assert all(a["org_id"] == 10 for a in sup)
    assert sup[0]["severity"] == "critical"  # most urgent first

    ph = {a["kind"] for a in client.get("/alerts", headers=PHARMACY).json()}
    assert {"budget_exceeded", "regular_item_unavailable", "order_awaiting_supplier"} <= ph

    sent = alerts_published()
    assert {e["payload"]["org_id"] for e in sent} == {10, 11, 20}
    # info alerts never trigger a notification
    assert not any("still waiting" in e["payload"]["title"] for e in sent)


def test_repeat_runs_do_not_spam_and_conditions_resolve(client, sources):
    run(client)
    first = len(alerts_published())
    run(client)
    assert len(alerts_published()) == first  # nothing new, nothing re-sent

    sources.products[0]["stock_available"] = 500  # Amoxil restocked
    sources.snapshot["budgets"] = []
    r = run(client)
    assert r["resolved"] >= 2
    kinds = {a["kind"] for a in client.get("/alerts", headers=SUPPLIER).json()}
    assert "out_of_stock" not in kinds
    resolved = client.get("/alerts", params={"state": "resolved"}, headers=SUPPLIER).json()
    assert any(a["kind"] == "out_of_stock" for a in resolved)


def test_escalation_reopens_acknowledged_alert_and_notifies(client, sources):
    sources.snapshot["budgets"][0]["committed"] = "850"  # 85% -> warning
    run(client)
    [budget] = [a for a in client.get("/alerts", headers=PHARMACY).json() if a["domain"] == "budget"]
    assert budget["severity"] == "warning"
    ack = client.post(f"/alerts/{budget['id']}/acknowledge", headers=PHARMACY)
    assert ack.json()["status"] == "ACKNOWLEDGED" and ack.json()["acknowledged_by"] == "Test User"

    before = len(alerts_published())
    sources.snapshot["budgets"][0]["committed"] = "1100"
    run(client)
    [budget] = [a for a in client.get("/alerts", headers=PHARMACY).json() if a["domain"] == "budget"]
    assert budget["severity"] == "critical" and budget["status"] == "OPEN"
    assert len(alerts_published()) == before + 1


def test_unreachable_source_keeps_its_alerts_and_alerts_operators(client, sources):
    run(client)
    stock_before = [a for a in client.get("/alerts", headers=SUPPLIER).json() if a["domain"] == "stock"]
    sources.fail.add("catalog")
    r = run(client)
    assert r["status"] == "PARTIAL" and any("catalog" in e for e in r["errors"])
    stock_after = [a for a in client.get("/alerts", headers=SUPPLIER).json() if a["domain"] == "stock"]
    assert len(stock_after) == len(stock_before)  # not resolved just because we couldn't look
    ops = client.get("/alerts", headers=ADMIN).json()
    assert any(a["kind"] == "monitoring_source_failed" for a in ops)

    sources.fail.clear()
    sources.down.add("orders")
    run(client)
    assert any(a["kind"] == "service_down" for a in client.get("/alerts", headers=ADMIN).json())


def test_notification_cap_per_org(client, sources, monkeypatch):
    monkeypatch.setattr(main.settings, "max_notifications_per_org_per_run", 1)
    run(client)
    to_supplier = [e["payload"] for e in alerts_published() if e["payload"]["org_id"] == 10]
    assert len(to_supplier) == 2 and "more alerts need attention" in to_supplier[1]["title"]


def test_alerts_are_private_to_each_organisation(client):
    run(client)
    mine = client.get("/alerts", headers=SUPPLIER).json()
    assert client.post(f"/alerts/{mine[0]['id']}/acknowledge", headers=OTHER_SUPPLIER).status_code == 404
    assert all(a["org_id"] == 11 for a in client.get("/alerts", headers=OTHER_SUPPLIER).json())
    summary = client.get("/alerts/summary", headers=SUPPLIER).json()
    assert summary["critical"] >= 3 and summary["total"] == len(mine)
    assert client.get("/admin/overview", headers=SUPPLIER).status_code == 403
    assert client.post("/internal/run").status_code == 403


def test_digest_uses_ai_but_only_keeps_grounded_actions(client):
    run(client)
    alerts = client.get("/alerts", headers=SUPPLIER).json()
    real = alerts[0]["id"]
    fake = FakeLLM([{"content": json.dumps({
        "headline": "Two medicines need restocking today",
        "summary": "Amoxil is out of stock and Panado runs out within a week.",
        "actions": [{"alert_id": real, "title": "Reorder Amoxil", "detail": "About 80 units."},
                    {"alert_id": 99999, "title": "Invented action", "detail": "Not grounded."}]})}])
    main.llm = fake
    d = client.post("/digest/refresh", headers=SUPPLIER).json()
    assert d["generated_by"] == "ai" and d["headline"].startswith("Two medicines")
    assert [a["alert_id"] for a in d["actions"]] == [real]
    assert d["actions"][0]["link"] == alerts[0]["link"]
    prompt = fake.calls[0]["messages"][1]["content"]
    assert "Amoxil" in prompt and fake.calls[0]["json_mode"] is True


def test_digest_falls_back_to_rules_when_ai_fails(client):
    run(client)
    main.llm = FakeLLM([LLMUnavailable("HTTP 402: Insufficient balance")])
    d = client.post("/digest/refresh", headers=PHARMACY).json()
    assert d["generated_by"] == "rules" and "urgent" in d["headline"]
    assert d["actions"]


def test_first_visit_digest_and_stale_flag(client, sources):
    d = client.get("/digest", headers=PHARMACY).json()
    assert d["headline"] == "All clear" and d["stale"] is False
    run(client)  # the scheduled run writes a fresh briefing because the alert set changed
    d2 = client.get("/digest", headers=PHARMACY).json()
    assert d2["id"] != d["id"] and d2["stale"] is False and d2["headline"] != "All clear"


class FakeUserApi:
    def __init__(self):
        self.calls = []

    def get(self, service, path, **params):
        self.calls.append((service, path, params))
        if path == "/budget":
            return {"amount": "1000.00", "committed": "1250.00", "percent_used": 125.0, "currency": "USD"}
        return {"items": [], "total": 0}

    def close(self):
        pass


def test_assistant_runs_tools_with_the_users_own_access(client, monkeypatch):
    run(client)
    fake = FakeLLM([
        {"content": None, "tool_calls": [
            {"id": "c1", "type": "function", "function": {"name": "get_budget", "arguments": "{}"}},
            {"id": "c2", "type": "function", "function": {"name": "get_inventory_alerts", "arguments": "{}"}}]},
        {"content": "You have used 125% of your USD 1,000 budget."},
    ])
    api = FakeUserApi()
    monkeypatch.setattr(main.assistant, "llm", fake)
    real_answer = main.assistant.answer
    monkeypatch.setattr(main.assistant, "answer", lambda s, p, token, history: real_answer(s, p, token, history, api))

    r = client.post("/assistant", headers=PHARMACY, json={"messages": [{"role": "user", "content": "How is my budget?"}]})
    assert r.status_code == 200, r.text
    assert r.json()["answer"].startswith("You have used 125%")
    assert r.json()["tools_used"] == ["get_budget", "get_inventory_alerts"]
    assert api.calls == [("orders", "/budget", {})]  # supplier-only tool was refused, not executed
    tool_msgs = [m for m in fake.calls[1]["messages"] if m["role"] == "tool"]
    assert "1250.00" in tool_msgs[0]["content"] and "not available" in tool_msgs[1]["content"]
    names = {t["function"]["name"] for t in fake.calls[0]["tools"]}
    assert "get_budget" in names and "get_inventory_alerts" not in names


def test_assistant_unavailable_without_key(client):
    r = client.post("/assistant", headers=PHARMACY, json={"messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 503
    assert client.get("/status", headers=PHARMACY).json()["ai_enabled"] is False


def test_admin_overview_and_metrics(client, sources):
    sources.down.add("notifications")
    run(client)
    o = client.get("/admin/overview", headers=ADMIN).json()
    assert o["services"]["notifications"]["up"] is False
    assert o["alerts_by_severity"]["critical"] >= 4 and o["runs"][0]["trigger"] == "external"
    assert client.post("/admin/run", headers=ADMIN).json()["trigger"] == "manual"
    text = client.get("/metrics").text
    assert 'multistock_agent_open_alerts{severity="critical"}' in text
    assert "multistock_agent_last_run_ok" in text


def test_lease_allows_only_one_runner(client):
    from app.engine import acquire_lease
    from app.models import Lease

    with main.db.SessionLocal() as s:
        assert acquire_lease(s, "monitor", "a", 60)
        assert acquire_lease(s, "monitor", "a", 60)  # holder renews
        assert not acquire_lease(s, "monitor", "b", 60)
        s.get(Lease, "monitor").expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        s.commit()
        assert acquire_lease(s, "monitor", "b", 60)  # expired -> taken over
