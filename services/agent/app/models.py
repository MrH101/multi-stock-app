from datetime import datetime
from enum import StrEnum

from sqlalchemy import JSON, DateTime, Enum, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from multistock_common.db import Base, TimestampMixin


class Severity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


SEVERITY_RANK = {Severity.INFO: 0, Severity.WARNING: 1, Severity.CRITICAL: 2}


class AlertStatus(StrEnum):
    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"


class Alert(TimestampMixin, Base):
    """One condition the agent is watching for one organisation.

    `key` identifies the condition (e.g. ``stock:12`` or ``budget:2026-11``) so repeated runs update the
    same alert instead of creating duplicates, and the alert resolves itself once the condition clears.
    """
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(Integer, index=True)
    key: Mapped[str] = mapped_column(String(120))
    domain: Mapped[str] = mapped_column(String(30), index=True)  # stock, expiry, order, budget, supply, platform
    kind: Mapped[str] = mapped_column(String(50))
    severity: Mapped[Severity] = mapped_column(Enum(Severity, native_enum=False))
    status: Mapped[AlertStatus] = mapped_column(Enum(AlertStatus, native_enum=False), default=AlertStatus.OPEN,
                                                index=True)
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(String(1000))
    link: Mapped[str | None] = mapped_column(String(300))
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notified_severity: Mapped[Severity | None] = mapped_column(Enum(Severity, native_enum=False))
    acknowledged_by: Mapped[str | None] = mapped_column(String(200))
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # "One live alert per (org, key)" is enforced by the engine; resolved rows are kept as history.


class Digest(TimestampMixin, Base):
    """The agent's written briefing for an organisation, regenerated when its alerts change."""
    __tablename__ = "digests"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(Integer, index=True)
    signature: Mapped[str] = mapped_column(String(64))  # hash of the alert set it describes
    headline: Mapped[str] = mapped_column(String(300))
    summary: Mapped[str] = mapped_column(Text)
    actions: Mapped[list] = mapped_column(JSON, default=list)
    generated_by: Mapped[str] = mapped_column(String(20))  # "ai" or "rules"
    model: Mapped[str | None] = mapped_column(String(120))


class RunStatus(StrEnum):
    RUNNING = "RUNNING"
    OK = "OK"
    PARTIAL = "PARTIAL"  # some sources were unreachable; their alerts were left untouched
    FAILED = "FAILED"


class MonitorRun(Base):
    __tablename__ = "monitor_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[float | None] = mapped_column(Float)
    status: Mapped[RunStatus] = mapped_column(Enum(RunStatus, native_enum=False), default=RunStatus.RUNNING)
    trigger: Mapped[str] = mapped_column(String(20), default="schedule")
    findings: Mapped[int] = mapped_column(Integer, default=0)
    opened: Mapped[int] = mapped_column(Integer, default=0)
    resolved: Mapped[int] = mapped_column(Integer, default=0)
    notified: Mapped[int] = mapped_column(Integer, default=0)
    digests: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[list] = mapped_column(JSON, default=list)


class Lease(Base):
    """Makes sure only one replica runs the monitoring loop at a time."""
    __tablename__ = "leases"

    name: Mapped[str] = mapped_column(String(50), primary_key=True)
    holder: Mapped[str] = mapped_column(String(100))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

