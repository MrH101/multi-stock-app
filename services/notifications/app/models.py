from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from multistock_common.auth import OrgType
from multistock_common.db import Base, TimestampMixin


class Notification(TimestampMixin, Base):
    """Addressed to an organisation; every user in it sees it and has their own read state."""
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(Integer, index=True)
    kind: Mapped[str] = mapped_column(String(50))  # order, message, broadcast, inventory
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(String(1000))
    link: Mapped[str | None] = mapped_column(String(300))  # frontend route, e.g. /orders/12


class NotificationReceipt(Base):
    __tablename__ = "notification_receipts"

    id: Mapped[int] = mapped_column(primary_key=True)
    notification_id: Mapped[int] = mapped_column(ForeignKey("notifications.id"), index=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)

    __table_args__ = (UniqueConstraint("notification_id", "user_id"),)


class Conversation(TimestampMixin, Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(primary_key=True)
    pharmacy_org_id: Mapped[int] = mapped_column(Integer, index=True)
    pharmacy_name: Mapped[str] = mapped_column(String(200))
    supplier_org_id: Mapped[int] = mapped_column(Integer, index=True)
    supplier_name: Mapped[str] = mapped_column(String(200))
    subject: Mapped[str] = mapped_column(String(200))
    order_number: Mapped[str | None] = mapped_column(String(40))
    pharmacy_last_read_id: Mapped[int] = mapped_column(Integer, default=0)
    supplier_last_read_id: Mapped[int] = mapped_column(Integer, default=0)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    messages: Mapped[list["ChatMessage"]] = relationship(back_populates="conversation", order_by="ChatMessage.id")


class ChatMessage(TimestampMixin, Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"), index=True)
    sender_org_id: Mapped[int] = mapped_column(Integer)
    sender_user_id: Mapped[int] = mapped_column(Integer)
    sender_name: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class Audience(StrEnum):
    ALL = "ALL"
    PHARMACIES = "PHARMACIES"
    SUPPLIERS = "SUPPLIERS"


class Broadcast(TimestampMixin, Base):
    __tablename__ = "broadcasts"

    id: Mapped[int] = mapped_column(primary_key=True)
    sender_org_id: Mapped[int] = mapped_column(Integer, index=True)
    sender_org_name: Mapped[str] = mapped_column(String(200))
    sender_org_type: Mapped[OrgType] = mapped_column(Enum(OrgType, native_enum=False))
    audience: Mapped[Audience] = mapped_column(Enum(Audience, native_enum=False))
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
