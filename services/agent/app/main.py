import asyncio
import logging
import os
import socket
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from multistock_common.app import create_app
from multistock_common.auth import CurrentUser, OrgType, Principal, require_org, require_service
from multistock_common.db import Database
from multistock_common.events import EventPublisher

from . import schemas
from .assistant import Assistant
from .config import settings
from .engine import (LIVE, Monitor, acquire_lease, latest_digest, live_alerts, now_utc, signature,
                     write_digest)
from .llm import CaimexClient, LLMUnavailable
from .models import SEVERITY_RANK, Alert, AlertStatus, MonitorRun, Severity
from .rules import as_utc
from .sources import InternalSources

log = logging.getLogger("agent")

db = Database(settings.database_url)
URLS = {"identity": settings.identity_url, "catalog": settings.catalog_url, "orders": settings.orders_url,
        "notifications": settings.notifications_url}
llm = CaimexClient(settings.caimex_api_key, settings.caimex_base_url, settings.caimex_model,
                   settings.caimex_fallback_models, settings.caimex_timeout_seconds)
events = EventPublisher(settings.redis_url, settings.event_stream, "agent",
                        settings.event_webhook_url, settings.service_token)
monitor = Monitor(db.SessionLocal, InternalSources(URLS, settings.service_token), llm, events, settings)
assistant = Assistant(llm, URLS, settings.assistant_max_steps)
INSTANCE = f"{socket.gethostname()}-{os.getpid()}"


def scheduled_run() -> None:
    with db.SessionLocal() as s:
        if not acquire_lease(s, "monitor", INSTANCE, settings.monitor_interval_seconds * 2):
            return  # another replica is the active monitor
    run = monitor.run("schedule")
    log.info("monitor run %s: %s, %s findings, %s opened, %s resolved, %s notified", run.id, run.status,
             run.findings, run.opened, run.resolved, run.notified)


async def scheduler() -> None:
    await asyncio.sleep(settings.monitor_initial_delay_seconds)
    while True:
        try:
            await run_in_threadpool(scheduled_run)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("scheduled monitor run crashed")
        await asyncio.sleep(settings.monitor_interval_seconds)


@asynccontextmanager
async def lifespan(_app):
    db.create_all()
    task = asyncio.create_task(scheduler()) if settings.monitor_enabled else None
    yield
    if task:
        task.cancel()


app = create_app(settings, "Monitoring Agent Service")
app.router.lifespan_context = lifespan
DB = Annotated[Session, Depends(db.session)]
Admin = Annotated[Principal, require_org(OrgType.PLATFORM)]


def _run_out(run: MonitorRun | None):
    return schemas.RunOut.model_validate(run) if run else None


def _last_run(s: Session) -> MonitorRun | None:
    return s.scalar(select(MonitorRun).order_by(MonitorRun.id.desc()).limit(1))


# ---------------------------------------------------------------- everyone
@app.get("/status", response_model=schemas.StatusOut, tags=["agent"])
def status(_p: CurrentUser, s: DB):
    return {"ai_enabled": llm.enabled, "model": llm.model if llm.enabled else None,
            "monitor_enabled": settings.monitor_enabled, "interval_minutes": settings.monitor_interval_seconds / 60,
            "last_run": _run_out(_last_run(s))}


@app.get("/alerts", response_model=list[schemas.AlertOut], tags=["alerts"])
def list_alerts(p: CurrentUser, s: DB, state: str = Query("live", pattern="^(live|resolved|all)$"),
                severity: Severity | None = None, domain: str | None = None, limit: int = Query(200, ge=1, le=500)):
    stmt = select(Alert).where(Alert.org_id == p.org_id)
    if state == "live":
        stmt = stmt.where(Alert.status.in_(LIVE))
    elif state == "resolved":
        stmt = stmt.where(Alert.status == AlertStatus.RESOLVED)
    if severity:
        stmt = stmt.where(Alert.severity == severity)
    if domain:
        stmt = stmt.where(Alert.domain == domain)
    rows = s.scalars(stmt.order_by(Alert.last_seen.desc()).limit(limit)).all()
    if state == "live":
        rows = sorted(rows, key=lambda a: (a.status != AlertStatus.OPEN, -SEVERITY_RANK[a.severity], a.first_seen))
    return rows


@app.get("/alerts/summary", response_model=schemas.AlertCounts, tags=["alerts"])
def alert_summary(p: CurrentUser, s: DB):
    counts = dict(s.execute(select(Alert.severity, func.count()).where(
        Alert.org_id == p.org_id, Alert.status == AlertStatus.OPEN).group_by(Alert.severity)).all())
    out = {sev.value: counts.get(sev, 0) for sev in Severity}
    return {**out, "total": sum(out.values())}


@app.post("/alerts/{alert_id}/acknowledge", response_model=schemas.AlertOut, tags=["alerts"])
def acknowledge(alert_id: int, p: CurrentUser, s: DB):
    a = s.get(Alert, alert_id)
    if not a or a.org_id != p.org_id:
        raise HTTPException(404, "Alert not found")
    if a.status == AlertStatus.RESOLVED:
        raise HTTPException(409, "This alert has already cleared")
    a.status, a.acknowledged_by, a.acknowledged_at = AlertStatus.ACKNOWLEDGED, p.name, now_utc()
    s.commit()
    return a


@app.get("/digest", response_model=schemas.DigestOut, tags=["briefing"])
def get_digest(p: CurrentUser, s: DB):
    d = latest_digest(s, p.org_id)
    alerts = live_alerts(s, p.org_id)
    if d is None:  # first visit: write a quick rule-based one; the AI version follows on the next run
        d = write_digest(s, _no_ai, p.org_id, p.org_name, p.org_type, alerts)
    out = schemas.DigestOut.model_validate(d)
    out.stale = d.signature != signature(alerts)
    return out


@app.post("/digest/refresh", response_model=schemas.DigestOut, tags=["briefing"])
async def refresh_digest(p: CurrentUser, s: DB):
    d = latest_digest(s, p.org_id)
    alerts = live_alerts(s, p.org_id)
    fresh = d and now_utc() - as_utc(d.created_at) < timedelta(seconds=60)
    if not (fresh and d.signature == signature(alerts) and (d.generated_by == "ai" or not llm.enabled)):
        d = await run_in_threadpool(write_digest, s, llm, p.org_id, p.org_name, p.org_type, alerts)
    return d


_recent_questions: dict[int, deque] = defaultdict(deque)


def _rate_limit(user_id: int, per_minute: int = 15) -> None:
    q, now = _recent_questions[user_id], time.monotonic()
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= per_minute:
        raise HTTPException(429, "You're asking very quickly. Please wait a moment and try again.")
    q.append(now)


@app.post("/assistant", response_model=schemas.AssistantOut, tags=["assistant"])
async def ask(body: schemas.AssistantIn, p: CurrentUser, s: DB, authorization: Annotated[str, Header()]):
    if body.messages[-1].role != "user":
        raise HTTPException(422, "The last message must be the user's question")
    _rate_limit(p.user_id)
    try:
        return await run_in_threadpool(assistant.answer, s, p, authorization[7:],
                                       [m.model_dump() for m in body.messages])
    except LLMUnavailable as exc:
        log.warning("assistant unavailable: %s", exc)
        raise HTTPException(503, "The assistant is unavailable right now. Your alerts and briefing still work.")


# ---------------------------------------------------------------- platform operators
@app.get("/admin/overview", response_model=schemas.OverviewOut, tags=["admin"])
async def overview(_p: Admin, s: DB):
    health = await run_in_threadpool(monitor.sources.health)
    sev = dict(s.execute(select(Alert.severity, func.count()).where(Alert.status.in_(LIVE))
                         .group_by(Alert.severity)).all())
    by_sev = {x.value: sev.get(x, 0) for x in Severity}
    by_domain = dict(s.execute(select(Alert.domain, func.count()).where(Alert.status.in_(LIVE))
                               .group_by(Alert.domain)).all())
    per_org: dict[int, dict] = defaultdict(lambda: {"critical": 0, "warning": 0, "info": 0})
    for org_id, severity, n in s.execute(select(Alert.org_id, Alert.severity, func.count())
                                         .where(Alert.status.in_(LIVE)).group_by(Alert.org_id, Alert.severity)):
        per_org[org_id][severity.value] = n
    top = sorted(({"org_id": k, **v} for k, v in per_org.items()),
                 key=lambda r: (r["critical"], r["warning"], r["info"]), reverse=True)[:10]
    st = llm.stats
    return {
        "services": health,
        "llm": {"enabled": llm.enabled, "model": llm.model, "fallback_models": llm.fallback_models,
                "requests": st.requests, "failures": st.failures, "cost_usd": round(st.cost_usd, 6),
                "last_model": st.last_model, "last_error": st.last_error},
        "runs": s.scalars(select(MonitorRun).order_by(MonitorRun.id.desc()).limit(10)).all(),
        "alerts_by_severity": {**by_sev, "total": sum(by_sev.values())},
        "alerts_by_domain": by_domain,
        "top_orgs": top,
    }


@app.post("/admin/run", response_model=schemas.RunOut, tags=["admin"])
async def run_now(_p: Admin):
    return await run_in_threadpool(monitor.run, "manual")


@app.post("/internal/run", response_model=schemas.RunOut, tags=["internal"], dependencies=[Depends(require_service)])
async def run_internal():
    """For an external scheduler (Kubernetes CronJob etc.) when MONITOR_ENABLED=false."""
    return await run_in_threadpool(monitor.run, "external")


# ---------------------------------------------------------------- Prometheus (blocked at the public gateway)
@app.get("/metrics", response_class=PlainTextResponse, tags=["ops"])
def metrics(s: DB):
    lines = []

    def metric(name: str, kind: str, help_: str, samples: list[tuple[dict, float]]):
        lines.append(f"# HELP {name} {help_}")
        lines.append(f"# TYPE {name} {kind}")
        for labels, value in samples:
            lbl = ",".join(f'{k}="{v}"' for k, v in labels.items())
            lines.append(f"{name}{{{lbl}}} {value}" if lbl else f"{name} {value}")

    sev = dict(s.execute(select(Alert.severity, func.count()).where(Alert.status.in_(LIVE))
                         .group_by(Alert.severity)).all())
    metric("multistock_agent_open_alerts", "gauge", "Live alerts by severity",
           [({"severity": x.value}, sev.get(x, 0)) for x in Severity])
    dom = s.execute(select(Alert.domain, func.count()).where(Alert.status.in_(LIVE)).group_by(Alert.domain)).all()
    metric("multistock_agent_open_alerts_by_domain", "gauge", "Live alerts by domain",
           [({"domain": d}, n) for d, n in dom])
    run = _last_run(s)
    if run and run.finished_at:
        metric("multistock_agent_last_run_timestamp_seconds", "gauge", "When the last run finished",
               [({}, as_utc(run.finished_at).timestamp())])
        metric("multistock_agent_last_run_duration_seconds", "gauge", "Duration of the last run",
               [({}, run.duration_seconds or 0)])
        metric("multistock_agent_last_run_ok", "gauge", "1 if the last run completed without errors",
               [({}, 1 if run.status == "OK" else 0)])
    runs = dict(s.execute(select(MonitorRun.status, func.count()).group_by(MonitorRun.status)).all())
    metric("multistock_agent_runs_total", "counter", "Monitoring runs by outcome",
           [({"status": k.value}, v) for k, v in runs.items()])
    st = llm.stats
    metric("multistock_agent_llm_requests_total", "counter", "Caimex requests", [({}, st.requests)])
    metric("multistock_agent_llm_failures_total", "counter", "Failed Caimex requests", [({}, st.failures)])
    metric("multistock_agent_llm_cost_usd_total", "counter", "Caimex spend reported by the gateway",
           [({}, round(st.cost_usd, 6))])
    return "\n".join(lines) + "\n"


class _NoAI:
    enabled = False


_no_ai = _NoAI()
