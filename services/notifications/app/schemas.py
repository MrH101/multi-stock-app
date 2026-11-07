from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from multistock_common.auth import OrgType

from .models import Audience


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    kind: str
    title: str
    body: str
    link: str | None
    created_at: datetime
    read: bool = False


class UnreadCount(BaseModel):
    notifications: int
    messages: int


class ConversationCreate(BaseModel):
    counterpart_org_id: int
    counterpart_org_name: str = Field(min_length=1, max_length=200)
    subject: str = Field(min_length=2, max_length=200)
    body: str = Field(min_length=1, max_length=5000)
    order_number: str | None = Field(None, max_length=40)


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    pharmacy_org_id: int
    pharmacy_name: str
    supplier_org_id: int
    supplier_name: str
    subject: str
    order_number: str | None
    last_message_at: datetime | None
    last_message_preview: str = ""
    unread: int = 0
    counterpart_name: str = ""


class MessageCreate(BaseModel):
    body: str = Field(min_length=1, max_length=5000)


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    conversation_id: int
    sender_org_id: int
    sender_name: str
    body: str
    created_at: datetime


class BroadcastCreate(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    body: str = Field(min_length=2, max_length=5000)
    audience: Audience = Audience.PHARMACIES


class BroadcastOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    sender_org_name: str
    sender_org_type: OrgType
    audience: Audience
    title: str
    body: str
    created_at: datetime
