from datetime import date
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import Boolean, Date, Enum, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from multistock_common.db import Base, TimestampMixin


class DosageForm(StrEnum):
    TABLET = "TABLET"
    CAPSULE = "CAPSULE"
    SYRUP = "SYRUP"
    SUSPENSION = "SUSPENSION"
    INJECTION_AMPOULE = "INJECTION_AMPOULE"
    INJECTION_VIAL = "INJECTION_VIAL"
    PEN = "PEN"
    CREAM_OINTMENT = "CREAM_OINTMENT"
    DROPS = "DROPS"
    INHALER = "INHALER"
    SUPPOSITORY = "SUPPOSITORY"
    PESSARY = "PESSARY"
    SURGICAL = "SURGICAL"
    OTHER = "OTHER"


class Schedule(StrEnum):
    """Regulatory class of the medicine."""
    OTC = "OTC"  # household / general sale
    P = "P"  # pharmacy only
    PP = "PP"  # pharmacist-initiated
    PRESCRIPTION = "PRESCRIPTION"
    CONTROLLED = "CONTROLLED"  # narcotics / psychotropics


class Product(TimestampMixin, Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    supplier_org_id: Mapped[int] = mapped_column(Integer, index=True)
    supplier_name: Mapped[str] = mapped_column(String(200))
    sku: Mapped[str | None] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(255), index=True)  # brand / trade name
    generic_name: Mapped[str | None] = mapped_column(String(255), index=True)
    strength: Mapped[str | None] = mapped_column(String(100))  # e.g. "500mg"
    dosage_form: Mapped[DosageForm] = mapped_column(Enum(DosageForm, native_enum=False), default=DosageForm.OTHER)
    pack_size: Mapped[str | None] = mapped_column(String(100))  # e.g. "10x10"
    manufacturer: Mapped[str | None] = mapped_column(String(200))
    schedule: Mapped[Schedule] = mapped_column(Enum(Schedule, native_enum=False), default=Schedule.P)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    description: Mapped[str | None] = mapped_column(Text)
    reorder_level: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    batches: Mapped[list["Batch"]] = relationship(back_populates="product", order_by="Batch.expiry_date")

    __table_args__ = (UniqueConstraint("supplier_org_id", "sku", name="uq_supplier_sku"),)


class Batch(TimestampMixin, Base):
    __tablename__ = "batches"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    batch_number: Mapped[str] = mapped_column(String(100))
    expiry_date: Mapped[date] = mapped_column(Date, index=True)
    quantity_available: Mapped[int] = mapped_column(Integer, default=0)
    quantity_reserved: Mapped[int] = mapped_column(Integer, default=0)

    product: Mapped[Product] = relationship(back_populates="batches")

    __table_args__ = (UniqueConstraint("product_id", "batch_number", name="uq_product_batch"),)


class MovementReason(StrEnum):
    RECEIVED = "RECEIVED"
    ADJUSTMENT = "ADJUSTMENT"
    DAMAGED = "DAMAGED"
    EXPIRED = "EXPIRED"
    RESERVED = "RESERVED"
    RELEASED = "RELEASED"
    DISPATCHED = "DISPATCHED"


class StockMovement(TimestampMixin, Base):
    """Append-only audit ledger: every change to a batch's stock is recorded here."""
    __tablename__ = "stock_movements"

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("batches.id"), index=True)
    change: Mapped[int] = mapped_column(Integer)
    reason: Mapped[MovementReason] = mapped_column(Enum(MovementReason, native_enum=False))
    reference: Mapped[str | None] = mapped_column(String(100))
    note: Mapped[str | None] = mapped_column(String(500))
    user_id: Mapped[int | None] = mapped_column(Integer)


class ReservationStatus(StrEnum):
    RESERVED = "RESERVED"
    RELEASED = "RELEASED"
    COMMITTED = "COMMITTED"


class Reservation(TimestampMixin, Base):
    __tablename__ = "reservations"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_ref: Mapped[str] = mapped_column(String(100), index=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("batches.id"))
    product_id: Mapped[int] = mapped_column(Integer)
    quantity: Mapped[int] = mapped_column(Integer)
    status: Mapped[ReservationStatus] = mapped_column(
        Enum(ReservationStatus, native_enum=False), default=ReservationStatus.RESERVED)

    batch: Mapped[Batch] = relationship()
