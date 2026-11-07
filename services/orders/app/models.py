from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import JSON, Date, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from multistock_common.db import Base, TimestampMixin


class OrderStatus(StrEnum):
    SUBMITTED = "SUBMITTED"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    DISPATCHED = "DISPATCHED"
    DELIVERED = "DELIVERED"
    CANCELLED = "CANCELLED"


class PaymentMethod(StrEnum):
    CASH_ON_DELIVERY = "CASH_ON_DELIVERY"
    BANK_TRANSFER = "BANK_TRANSFER"
    ON_ACCOUNT = "ON_ACCOUNT"
    MOBILE_MONEY = "MOBILE_MONEY"


class Order(TimestampMixin, Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_number: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    checkout_ref: Mapped[str] = mapped_column(String(64), index=True)
    pharmacy_org_id: Mapped[int] = mapped_column(Integer, index=True)
    pharmacy_name: Mapped[str] = mapped_column(String(200))
    supplier_org_id: Mapped[int] = mapped_column(Integer, index=True)
    supplier_name: Mapped[str] = mapped_column(String(200))
    created_by_user_id: Mapped[int] = mapped_column(Integer)
    created_by_name: Mapped[str] = mapped_column(String(200))
    status: Mapped[OrderStatus] = mapped_column(Enum(OrderStatus, native_enum=False), default=OrderStatus.SUBMITTED, index=True)
    payment_method: Mapped[PaymentMethod] = mapped_column(Enum(PaymentMethod, native_enum=False))
    delivery_address: Mapped[str] = mapped_column(String(500))
    contact_name: Mapped[str] = mapped_column(String(200))
    contact_phone: Mapped[str] = mapped_column(String(50))
    notes: Mapped[str | None] = mapped_column(Text)
    currency: Mapped[str] = mapped_column(String(3))
    subtotal: Mapped[Decimal] = mapped_column(Numeric(14, 2))

    lines: Mapped[list["OrderLine"]] = relationship(back_populates="order", cascade="all, delete-orphan")
    history: Mapped[list["OrderEvent"]] = relationship(back_populates="order", cascade="all, delete-orphan",
                                                       order_by="OrderEvent.id")


class OrderLine(Base):
    __tablename__ = "order_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    product_id: Mapped[int] = mapped_column(Integer)
    product_name: Mapped[str] = mapped_column(String(255))
    generic_name: Mapped[str | None] = mapped_column(String(255))
    strength: Mapped[str | None] = mapped_column(String(100))
    pack_size: Mapped[str | None] = mapped_column(String(100))
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    line_total: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    schedule: Mapped[str | None] = mapped_column(String(20))  # MCAZ supply category at time of order
    mcaz_registration_number: Mapped[str | None] = mapped_column(String(60))
    # batch numbers + expiry dates allocated by the catalog (traceability for recalls)
    allocations: Mapped[list] = mapped_column(JSON, default=list)

    order: Mapped[Order] = relationship(back_populates="lines")


class OrderEvent(Base):
    __tablename__ = "order_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    status: Mapped[OrderStatus] = mapped_column(Enum(OrderStatus, native_enum=False))
    note: Mapped[str | None] = mapped_column(String(500))
    actor_name: Mapped[str] = mapped_column(String(200))
    actor_org_name: Mapped[str] = mapped_column(String(200))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    order: Mapped[Order] = relationship(back_populates="history")


class Budget(TimestampMixin, Base):
    """Monthly purchasing budget for a pharmacy."""
    __tablename__ = "budgets"

    id: Mapped[int] = mapped_column(primary_key=True)
    pharmacy_org_id: Mapped[int] = mapped_column(Integer, index=True)
    period: Mapped[date] = mapped_column(Date)  # first day of month
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3), default="USD")

    __table_args__ = (UniqueConstraint("pharmacy_org_id", "period", name="uq_budget_period"),)
