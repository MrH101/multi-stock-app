"""Deterministic monitoring rules.

Every rule is a pure function from service snapshots to ``Finding``s, which makes the thresholds easy to
test and audit. A finding's ``key`` names the condition being tracked; the engine uses it to update,
escalate and auto-resolve alerts across runs.
"""
import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal

from .config import Settings
from .models import Severity


@dataclass
class Finding:
    org_id: int
    key: str
    kind: str
    severity: Severity
    title: str
    body: str
    link: str | None = None
    metrics: dict = field(default_factory=dict)

    @property
    def domain(self) -> str:
        return self.key.split(":", 1)[0]


def _date(v) -> date | None:
    if v is None or isinstance(v, date) and not isinstance(v, datetime):
        return v
    return date.fromisoformat(str(v)[:10])


def as_utc(v) -> datetime:
    dt = v if isinstance(v, datetime) else datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _money(amount, currency: str) -> str:
    return f"{currency} {Decimal(str(amount)):,.2f}"


def _units(n: float) -> str:
    n = int(round(n))
    return f"{n:,} unit{'s' if n != 1 else ''}"


def _label(p: dict) -> str:
    name = p.get("name") or f"Product {p.get('id')}"
    strength = p.get("strength")
    return f"{name} {strength}" if strength and strength.lower() not in name.lower() else name


# ---------------------------------------------------------------- suppliers: stock levels
def stock_levels(inventory: dict, cfg: Settings) -> list[Finding]:
    days = inventory.get("demand_days") or cfg.supplier_demand_days
    out = []
    for p in inventory.get("products", []):
        stock, reorder, demand = p["stock_available"], p.get("reorder_level") or 0, p.get("demand_units") or 0
        daily = demand / days if demand else 0.0
        cover = stock / daily if daily else None
        name = _label(p)
        metrics = {"product_id": p["id"], "stock": stock, "reorder_level": reorder, "demand_units": demand,
                   "demand_days": days, "daily_demand": round(daily, 2),
                   "days_of_cover": round(cover, 1) if cover is not None else None}
        target = math.ceil(daily * cfg.reorder_target_days + reorder - stock) if (daily or reorder) else 0
        suggestion = f" Suggested replenishment: about {_units(target)}." if target > 0 else ""
        demand_text = f" Pharmacies reserved {_units(demand)} in the last {days} days." if demand else ""
        common = dict(org_id=p["supplier_org_id"], key=f"stock:{p['id']}", link=f"/inventory/{p['id']}",
                      metrics={**metrics, "suggested_reorder": max(target, 0)})

        if stock <= 0 and (reorder > 0 or demand > 0):
            out.append(Finding(kind="out_of_stock", severity=Severity.CRITICAL, title=f"{name} is out of stock",
                               body=f"No sellable stock left, so pharmacies cannot order it.{demand_text}{suggestion}",
                               **common))
        elif cover is not None and cover < cfg.cover_critical_days:
            out.append(Finding(kind="low_cover", severity=Severity.CRITICAL,
                               title=f"{name} runs out in about {max(cover, 0.5):.0f} days",
                               body=f"{_units(stock)} left at about {daily:.1f} a day.{suggestion}", **common))
        elif cover is not None and cover < cfg.cover_warning_days:
            out.append(Finding(kind="low_cover", severity=Severity.WARNING,
                               title=f"{name} has about {cover:.0f} days of stock left",
                               body=f"{_units(stock)} left at about {daily:.1f} a day.{suggestion}", **common))
        elif reorder > 0 and stock <= reorder:
            out.append(Finding(kind="below_reorder", severity=Severity.WARNING,
                               title=f"{name} is below its reorder level",
                               body=f"{_units(stock)} left; reorder level is {reorder:,}.{suggestion}", **common))
    return out


# ---------------------------------------------------------------- suppliers: expiry
def expiry(inventory: dict, cfg: Settings, today: date | None = None) -> list[Finding]:
    today = today or _date(inventory.get("as_of")) or date.today()
    days = inventory.get("demand_days") or cfg.supplier_demand_days
    daily = {p["id"]: (p.get("demand_units") or 0) / days for p in inventory.get("products", [])}
    out = []
    for b in inventory.get("batches", []):
        left = (_date(b["expiry_date"]) - today).days
        qty, name = b["quantity_available"], b["product_name"]
        value = _money(b.get("value", 0), b.get("currency", "USD"))
        common = dict(org_id=b["supplier_org_id"], key=f"expiry:{b['batch_id']}", link=f"/inventory/{b['product_id']}",
                      metrics={"batch_id": b["batch_id"], "batch_number": b["batch_number"], "days_to_expiry": left,
                               "quantity": qty, "value": str(b.get("value", 0)), "expiry_date": str(b["expiry_date"])})
        if left <= 0:
            out.append(Finding(kind="expired_on_hand", severity=Severity.CRITICAL,
                               title=f"Expired stock on hand: {name} batch {b['batch_number']}",
                               body=f"{_units(qty)} ({value}) expired on {b['expiry_date']}. It is excluded from "
                                    "orders automatically. Quarantine it and record the write-off.", **common))
            continue
        if left > cfg.expiry_warning_days:
            continue
        sell_through = daily.get(b["product_id"], 0) * left
        unsold = max(qty - sell_through, 0)
        risk = (f" At current demand about {_units(unsold)} will not sell in time. Consider a promotion, "
                "redistribution or a return to the manufacturer.") if unsold >= 1 else \
            " Current demand should clear it before expiry."
        severity = Severity.CRITICAL if left <= cfg.expiry_critical_days else Severity.WARNING
        out.append(Finding(kind="expiring", severity=severity,
                           title=f"{name} batch {b['batch_number']} expires in {left} days",
                           body=f"{_units(qty)} ({value}) expire on {b['expiry_date']}.{risk}",
                           **{**common, "metrics": {**common["metrics"], "units_at_risk": round(unsold)}}))
    return out


# ---------------------------------------------------------------- orders: service levels
def order_sla(snapshot: dict, cfg: Settings, now: datetime | None = None) -> list[Finding]:
    now = now or datetime.now(timezone.utc)
    out = []
    for o in snapshot.get("open_orders", []):
        hours = (now - as_utc(o["status_since"])).total_seconds() / 3600
        num, link = o["order_number"], f"/orders/{o['id']}"
        metrics = {"order_id": o["id"], "order_number": num, "status": o["status"], "hours_in_status": round(hours, 1),
                   "subtotal": str(o["subtotal"]), "currency": o["currency"]}
        if o["status"] == "SUBMITTED" and hours >= cfg.order_review_sla_hours:
            sev = Severity.CRITICAL if hours >= 2 * cfg.order_review_sla_hours else Severity.WARNING
            out.append(Finding(o["supplier_org_id"], f"order:{o['id']}:review", "order_review_overdue", sev,
                               f"Order {num} from {o['pharmacy_name']} has waited {hours:.0f}h for review",
                               f"Accept or reject it so the pharmacy can plan; stock stays reserved meanwhile.",
                               link, metrics))
            out.append(Finding(o["pharmacy_org_id"], f"order:{o['id']}:awaiting", "order_awaiting_supplier",
                               Severity.INFO, f"Order {num} is still waiting for {o['supplier_name']}",
                               f"Submitted {hours:.0f}h ago with no response. You can message the supplier "
                               "from the order page.", link, metrics))
        elif o["status"] == "ACCEPTED" and hours >= cfg.order_dispatch_sla_hours:
            out.append(Finding(o["supplier_org_id"], f"order:{o['id']}:dispatch", "order_dispatch_overdue",
                               Severity.WARNING, f"Order {num} was accepted {hours:.0f}h ago but not dispatched",
                               f"{o['pharmacy_name']} is waiting for delivery.", link, metrics))
        elif o["status"] == "DISPATCHED" and hours >= cfg.order_delivery_sla_hours:
            out.append(Finding(o["pharmacy_org_id"], f"order:{o['id']}:delivery", "order_delivery_unconfirmed",
                               Severity.WARNING, f"Please confirm delivery of order {num}",
                               f"It was dispatched {hours:.0f}h ago. Mark it delivered once received, or contact "
                               f"{o['supplier_name']} if it has not arrived.", link, metrics))
    return out


# ---------------------------------------------------------------- pharmacies: budgets
def budgets(snapshot: dict, cfg: Settings) -> list[Finding]:
    out = []
    for b in snapshot.get("budgets", []):
        amount, committed = Decimal(str(b["amount"])), Decimal(str(b["committed"]))
        if amount <= 0:
            continue
        pct = float(committed / amount * 100)
        elapsed, length = b.get("days_elapsed") or 1, b.get("days_in_month") or 30
        projected = committed / elapsed * length
        cur = b["currency"]
        period = str(b["period"])[:7]
        metrics = {"amount": str(amount), "committed": str(committed), "percent_used": round(pct, 1),
                   "projected": str(projected.quantize(Decimal("0.01"))), "currency": cur,
                   "days_elapsed": elapsed, "days_in_month": length}
        common = dict(org_id=b["pharmacy_org_id"], key=f"budget:{period}", link="/", metrics=metrics)
        left = f"{_money(committed, cur)} of {_money(amount, cur)} committed"
        if pct >= 100:
            out.append(Finding(kind="budget_exceeded", severity=Severity.CRITICAL,
                               title=f"Monthly budget exceeded ({pct:.0f}%)",
                               body=f"{left}, {_money(committed - amount, cur)} over. New orders still go through; "
                                    "an owner or manager can review spend or raise the budget.", **common))
        elif pct >= cfg.budget_warning_percent:
            out.append(Finding(kind="budget_high", severity=Severity.WARNING,
                               title=f"{pct:.0f}% of this month's budget used",
                               body=f"{left}; {_money(amount - committed, cur)} left for the "
                                    f"remaining {length - elapsed} days.", **common))
        elif elapsed >= 5 and projected > amount:
            out.append(Finding(kind="budget_projection", severity=Severity.WARNING,
                               title="On track to go over this month's budget",
                               body=f"{left}. At the current pace you will spend about {_money(projected, cur)} "
                                    f"this month, {_money(projected - amount, cur)} over budget.", **common))
        elif pct >= cfg.budget_info_percent:
            out.append(Finding(kind="budget_half", severity=Severity.INFO, title=f"{pct:.0f}% of this month's budget used",
                               body=f"{left}. Spending is on pace to stay within budget.", **common))
    return out


# ---------------------------------------------------------------- pharmacies: supply of items they rely on
def supply_watch(snapshot: dict, inventory: dict) -> list[Finding]:
    products = {p["id"]: p for p in inventory.get("products", [])}
    by_generic: dict[tuple, list[dict]] = defaultdict(list)
    for p in products.values():
        if p.get("generic_name") and p["stock_available"] > 0:
            by_generic[((p["generic_name"] or "").lower(), (p.get("strength") or "").lower())].append(p)
    out = []
    for d in snapshot.get("demand", []):
        if d["order_count"] < 2:  # only items the pharmacy orders regularly
            continue
        p = products.get(d["product_id"])
        if p is None:
            continue
        typical = d["quantity"] / d["order_count"]
        stock = p["stock_available"]
        if stock >= typical:
            continue
        alts = [a for a in by_generic.get(((p.get("generic_name") or "").lower(), (p.get("strength") or "").lower()), [])
                if a["id"] != p["id"] and a["stock_available"] >= typical]
        alt_text = (" In stock elsewhere: " + "; ".join(f"{a['name']} from {a['supplier_name']}" for a in alts[:3]) + ".") \
            if alts else ""
        metrics = {"product_id": p["id"], "supplier_stock": stock, "typical_order": round(typical),
                   "orders_last_period": d["order_count"], "alternatives": [a["id"] for a in alts[:3]]}
        if stock <= 0:
            out.append(Finding(d["pharmacy_org_id"], f"supply:{p['id']}", "regular_item_unavailable", Severity.WARNING,
                               f"{p['name']} is out of stock at {p['supplier_name']}",
                               f"You have ordered it {d['order_count']} times recently.{alt_text}", "/catalog", metrics))
        else:
            out.append(Finding(d["pharmacy_org_id"], f"supply:{p['id']}", "regular_item_scarce", Severity.INFO,
                               f"Only {stock:,} of {p['name']} left at {p['supplier_name']}",
                               f"Your usual order is about {typical:.0f}.{alt_text}", "/catalog", metrics))
    return out


# ---------------------------------------------------------------- platform operators
def platform_health(platform_org_id: int | None, health: dict[str, dict], source_errors: list[str],
                    llm_enabled: bool, llm_error: str | None) -> list[Finding]:
    if platform_org_id is None:
        return []
    out = []
    for name, h in health.items():
        if not h["up"]:
            out.append(Finding(platform_org_id, f"platform:{name}", "service_down", Severity.CRITICAL,
                               f"The {name} service is not responding",
                               f"Health check failed ({h.get('detail') or 'no response'}). Users may be unable to use "
                               f"features that depend on it.", "/monitoring", {"service": name, **h}))
    for err in source_errors:
        src = err.split(":", 1)[0]
        if health.get(src, {}).get("up", True):
            out.append(Finding(platform_org_id, f"platform:source:{src}", "monitoring_source_failed", Severity.WARNING,
                               f"Monitoring could not read data from {src}", err[:900], "/monitoring", {"source": src}))
    if llm_enabled and llm_error:
        out.append(Finding(platform_org_id, "platform:llm", "llm_unavailable", Severity.WARNING,
                           "AI briefings are falling back to rule-based text",
                           f"Caimex requests are failing: {llm_error[:600]}", "/monitoring", {}))
    return out
