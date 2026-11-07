from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import JSON, Boolean, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from multistock_common.db import Base, TimestampMixin


class MerchantAccount(TimestampMixin, Base):
    """Where a supplier receives money in one currency. Paynow issues one integration per currency."""
    __tablename__ = "merchant_accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    supplier_org_id: Mapped[int] = mapped_column(Integer, index=True)
    currency: Mapped[str] = mapped_column(String(3))
    paynow_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    paynow_integration_id: Mapped[str | None] = mapped_column(String(40))
    paynow_integration_key_enc: Mapped[str | None] = mapped_column(Text)  # Fernet-encrypted
    bank_name: Mapped[str | None] = mapped_column(String(120))
    bank_account_name: Mapped[str | None] = mapped_column(String(200))
    bank_account_number: Mapped[str | None] = mapped_column(String(60))
    bank_branch: Mapped[str | None] = mapped_column(String(120))
    payment_instructions: Mapped[str | None] = mapped_column(String(500))

    __table_args__ = (UniqueConstraint("supplier_org_id", "currency", name="uq_merchant_currency"),)


class Method(StrEnum):
    ECOCASH = "ecocash"
    ONEMONEY = "onemoney"
    INNBUCKS = "innbucks"
    PAYNOW_WEB = "paynow_web"  # card, ZimSwitch and other methods on Paynow's own page
    BANK_TRANSFER = "bank_transfer"  # proof of payment uploaded by the pharmacy


MOBILE = {Method.ECOCASH, Method.ONEMONEY, Method.INNBUCKS}


class PayStatus(StrEnum):
    CREATED = "CREATED"
    PENDING = "PENDING"  # sent to Paynow, waiting for the customer
    AWAITING_CONFIRMATION = "AWAITING_CONFIRMATION"  # proof of payment, waiting for the supplier
    PAID = "PAID"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"  # supplier rejected the proof of payment
    DISPUTED = "DISPUTED"  # amount mismatch or a provider dispute: needs a human
    REFUNDED = "REFUNDED"


FINAL = {PayStatus.PAID, PayStatus.FAILED, PayStatus.CANCELLED, PayStatus.REJECTED, PayStatus.REFUNDED}
OPEN = {PayStatus.CREATED, PayStatus.PENDING, PayStatus.AWAITING_CONFIRMATION}


class Payment(TimestampMixin, Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    reference: Mapped[str] = mapped_column(String(40), unique=True, index=True)  # our ref sent to Paynow
    order_id: Mapped[int] = mapped_column(Integer)
    order_number: Mapped[str] = mapped_column(String(40), index=True)
    pharmacy_org_id: Mapped[int] = mapped_column(Integer, index=True)
    supplier_org_id: Mapped[int] = mapped_column(Integer, index=True)
    merchant_account_id: Mapped[int | None] = mapped_column(ForeignKey("merchant_accounts.id"))
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3))
    method: Mapped[Method] = mapped_column(Enum(Method, native_enum=False, length=20))
    status: Mapped[PayStatus] = mapped_column(Enum(PayStatus, native_enum=False, length=30), default=PayStatus.CREATED,
                                              index=True)
    phone: Mapped[str | None] = mapped_column(String(20))
    provider_reference: Mapped[str | None] = mapped_column(String(60))  # paynowreference
    provider_status: Mapped[str | None] = mapped_column(String(40))
    poll_url: Mapped[str | None] = mapped_column(String(500))
    redirect_url: Mapped[str | None] = mapped_column(String(500))
    instructions: Mapped[str | None] = mapped_column(Text)
    innbucks_code: Mapped[str | None] = mapped_column(String(40))
    innbucks_expires: Mapped[str | None] = mapped_column(String(40))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_user_id: Mapped[int] = mapped_column(Integer)
    created_by_name: Mapped[str] = mapped_column(String(200))
    note: Mapped[str | None] = mapped_column(String(500))
    error: Mapped[str | None] = mapped_column(String(500))

    proofs: Mapped[list["ProofOfPayment"]] = relationship(back_populates="payment", order_by="ProofOfPayment.id")
    events: Mapped[list["PaymentEvent"]] = relationship(back_populates="payment", order_by="PaymentEvent.id")


class ProofOfPayment(TimestampMixin, Base):
    __tablename__ = "proofs_of_payment"

    id: Mapped[int] = mapped_column(primary_key=True)
    payment_id: Mapped[int] = mapped_column(ForeignKey("payments.id"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    stored_as: Mapped[str] = mapped_column(String(100))
    content_type: Mapped[str] = mapped_column(String(60))
    size: Mapped[int] = mapped_column(Integer)
    bank_reference: Mapped[str | None] = mapped_column(String(100))
    uploaded_by: Mapped[str] = mapped_column(String(200))
    reviewed_by: Mapped[str | None] = mapped_column(String(200))
    review_note: Mapped[str | None] = mapped_column(String(500))

    payment: Mapped[Payment] = relationship(back_populates="proofs")


class PaymentEvent(Base):
    """Audit trail: every status change and every message from the provider."""
    __tablename__ = "payment_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    payment_id: Mapped[int] = mapped_column(ForeignKey("payments.id"), index=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(30))
    source: Mapped[str] = mapped_column(String(30))  # initiate, callback, poll, supplier, system
    detail: Mapped[dict] = mapped_column(JSON, default=dict)

    payment: Mapped[Payment] = relationship(back_populates="events")
