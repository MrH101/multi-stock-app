from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .models import AlertStatus, RunStatus, Severity


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class AlertOut(ORM):
    id: int
    org_id: int
    domain: str
    kind: str
    severity: Severity
    status: AlertStatus
    title: str
    body: str
    link: str | None
    metrics: dict
    first_seen: datetime
    last_seen: datetime
    resolved_at: datetime | None
    acknowledged_by: str | None
    acknowledged_at: datetime | None


class AlertCounts(BaseModel):
    critical: int = 0
    warning: int = 0
    info: int = 0
    total: int = 0


class DigestAction(BaseModel):
    title: str
    detail: str
    alert_id: int | None = None
    link: str | None = None


class DigestOut(ORM):
    id: int
    headline: str
    summary: str
    actions: list[DigestAction]
    generated_by: Literal["ai", "rules"]
    model: str | None
    created_at: datetime
    stale: bool = False  # alerts changed since it was written; a newer one is on its way


class RunOut(ORM):
    id: int
    started_at: datetime
    finished_at: datetime | None
    duration_seconds: float | None
    status: RunStatus
    trigger: str
    findings: int
    opened: int
    resolved: int
    notified: int
    digests: int
    errors: list[str]


class StatusOut(BaseModel):
    ai_enabled: bool
    model: str | None
    monitor_enabled: bool
    interval_minutes: float
    last_run: RunOut | None


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class AssistantIn(BaseModel):
    messages: list[ChatTurn] = Field(min_length=1, max_length=30)


class AssistantOut(BaseModel):
    answer: str
    model: str | None
    tools_used: list[str]


class ServiceHealth(BaseModel):
    up: bool
    latency_ms: float | None
    detail: str | None


class LLMStatus(BaseModel):
    enabled: bool
    model: str
    fallback_models: list[str]
    requests: int
    failures: int
    cost_usd: float
    last_model: str | None
    last_error: str | None


class OrgAlertCount(BaseModel):
    org_id: int
    critical: int
    warning: int
    info: int


class OverviewOut(BaseModel):
    services: dict[str, ServiceHealth]
    llm: LLMStatus
    runs: list[RunOut]
    alerts_by_severity: AlertCounts
    alerts_by_domain: dict[str, int]
    top_orgs: list[OrgAlertCount]
