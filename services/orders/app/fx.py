"""Exchange rates (issue #4).

Zimbabwe trades in USD and ZiG (ISO code ZWG) side by side, and some suppliers quote in ZAR. Rates are
stored as *units of currency per 1 USD*, set by platform operators each day (e.g. from the RBZ interbank
rate). Every order keeps a snapshot of the rates used at checkout, so historic totals never move when
today's rate changes.
"""
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import Date, Integer, Numeric, String, func, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from multistock_common.db import Base, TimestampMixin

BASE = "USD"
SUPPORTED = ("USD", "ZWG", "ZAR")
CENT = Decimal("0.01")


class ExchangeRate(TimestampMixin, Base):
    __tablename__ = "exchange_rates"

    id: Mapped[int] = mapped_column(primary_key=True)
    currency: Mapped[str] = mapped_column(String(3), index=True)
    per_usd: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    effective_date: Mapped[date] = mapped_column(Date, index=True)
    source: Mapped[str | None] = mapped_column(String(120))
    set_by: Mapped[str | None] = mapped_column(String(200))
    set_by_user_id: Mapped[int | None] = mapped_column(Integer)


def latest(s: Session) -> dict[str, ExchangeRate]:
    newest = (select(ExchangeRate.currency, func.max(ExchangeRate.id).label("id"))
              .group_by(ExchangeRate.currency).subquery())
    rows = s.scalars(select(ExchangeRate).join(newest, newest.c.id == ExchangeRate.id)).all()
    return {r.currency: r for r in rows}


def current_rates(s: Session) -> dict[str, Decimal]:
    return {BASE: Decimal(1), **{c: r.per_usd for c, r in latest(s).items()}}


def snapshot(rates: dict[str, Decimal]) -> dict[str, str]:
    return {c: str(v) for c, v in rates.items()}


def parse(snap: dict | None) -> dict[str, Decimal]:
    return {BASE: Decimal(1), **{c: Decimal(str(v)) for c, v in (snap or {}).items()}}


def convert(amount, frm: str, to: str, rates: dict[str, Decimal]) -> Decimal | None:
    """Convert via USD. Returns None when a needed rate is unknown."""
    amount = Decimal(str(amount))
    if frm == to:
        return amount
    if frm not in rates or to not in rates or not rates[frm]:
        return None
    return (amount / rates[frm] * rates[to]).quantize(CENT, rounding=ROUND_HALF_UP)


def info(s: Session) -> dict:
    rows = latest(s)
    return {
        "base": BASE,
        "rates": {BASE: "1", **{c: str(r.per_usd) for c, r in rows.items()}},
        "as_of": {c: r.effective_date for c, r in rows.items()},
        "updated_at": max((r.created_at for r in rows.values()), default=None),
        "source": {c: r.source for c, r in rows.items()},
        "supported": list(SUPPORTED),
    }
