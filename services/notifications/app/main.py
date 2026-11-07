import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from multistock_common.auth import (CurrentUser, OrgType, Principal, decode_token, principal_from_claims,
                                    require_org, require_service)
from multistock_common.app import create_app
from multistock_common.db import Database

from . import schemas
from .config import settings
from .handlers import handle_event, notify
from .models import Audience, Broadcast, ChatMessage, Conversation, Notification, NotificationReceipt
from .realtime import manager

db = Database(settings.database_url)


@asynccontextmanager
async def lifespan(_app):
    db.create_all()
    manager.loop = asyncio.get_running_loop()
    task = None
    if settings.redis_url:
        from .consumer import consume_forever
        task = asyncio.create_task(consume_forever(db.SessionLocal))
    yield
    if task:
        task.cancel()


app = create_app(settings, "Notifications & Messaging Service")
app.router.lifespan_context = lifespan
DB = Annotated[Session, Depends(db.session)]


# ---------------------------------------------------------------- realtime
@app.websocket("/ws")
async def websocket(ws: WebSocket, token: str = Query(...)):
    try:
        p = principal_from_claims(decode_token(token, settings.jwt_secret, settings.jwt_algorithm))
    except Exception:
        await ws.close(code=4401)
        return
    await manager.connect(p.org_id, ws)
    try:
        while True:
            await ws.receive_text()  # keep-alive pings from the client
    except WebSocketDisconnect:
        manager.disconnect(p.org_id, ws)


# ---------------------------------------------------------------- notifications
def _unread_stmt(p: Principal):
    read = select(NotificationReceipt.notification_id).where(NotificationReceipt.user_id == p.user_id)
    return select(Notification).where(Notification.org_id == p.org_id, Notification.id.not_in(read))


@app.get("/notifications", response_model=list[schemas.NotificationOut], tags=["notifications"])
def list_notifications(p: CurrentUser, s: DB, unread_only: bool = False, limit: int = Query(30, le=100)):
    stmt = _unread_stmt(p) if unread_only else select(Notification).where(Notification.org_id == p.org_id)
    rows = s.scalars(stmt.order_by(Notification.id.desc()).limit(limit)).all()
    read_ids = set(s.scalars(select(NotificationReceipt.notification_id).where(
        NotificationReceipt.user_id == p.user_id, NotificationReceipt.notification_id.in_([n.id for n in rows]))))
    return [{**schemas.NotificationOut.model_validate(n).model_dump(), "read": n.id in read_ids} for n in rows]


@app.get("/unread", response_model=schemas.UnreadCount, tags=["notifications"])
def unread_counts(p: CurrentUser, s: DB):
    n = s.scalar(select(func.count()).select_from(_unread_stmt(p).subquery()))
    return {"notifications": n, "messages": sum(c["unread"] for c in _conversations(s, p))}


@app.post("/notifications/{notification_id}/read", status_code=204, tags=["notifications"])
def mark_read(notification_id: int, p: CurrentUser, s: DB):
    n = s.get(Notification, notification_id)
    if not n or n.org_id != p.org_id:
        raise HTTPException(404, "Notification not found")
    if not s.scalar(select(NotificationReceipt).where(NotificationReceipt.notification_id == n.id,
                                                      NotificationReceipt.user_id == p.user_id)):
        s.add(NotificationReceipt(notification_id=n.id, user_id=p.user_id))
        s.commit()


@app.post("/notifications/read-all", status_code=204, tags=["notifications"])
def mark_all_read(p: CurrentUser, s: DB):
    for n in s.scalars(_unread_stmt(p)).all():
        s.add(NotificationReceipt(notification_id=n.id, user_id=p.user_id))
    s.commit()


# ---------------------------------------------------------------- messaging
def _conversations(s: Session, p: Principal) -> list[dict]:
    col = Conversation.pharmacy_org_id if p.is_pharmacy else Conversation.supplier_org_id
    convs = s.scalars(select(Conversation).where(col == p.org_id)
                      .order_by(Conversation.last_message_at.desc())).all()
    out = []
    for c in convs:
        last_read = c.pharmacy_last_read_id if p.is_pharmacy else c.supplier_last_read_id
        unread = s.scalar(select(func.count()).where(
            ChatMessage.conversation_id == c.id, ChatMessage.id > last_read,
            ChatMessage.sender_org_id != p.org_id))
        last = c.messages[-1] if c.messages else None
        out.append({**schemas.ConversationOut.model_validate(c).model_dump(), "unread": unread,
                    "last_message_preview": (last.body[:120] if last else ""),
                    "counterpart_name": c.supplier_name if p.is_pharmacy else c.pharmacy_name})
    return out


def _get_conversation(s: Session, cid: int, p: Principal) -> Conversation:
    c = s.get(Conversation, cid)
    if not c or p.org_id not in (c.pharmacy_org_id, c.supplier_org_id):
        raise HTTPException(404, "Conversation not found")
    return c


def _post_message(s: Session, c: Conversation, p: Principal, body: str) -> ChatMessage:
    m = ChatMessage(conversation_id=c.id, sender_org_id=p.org_id, sender_user_id=p.user_id,
                    sender_name=f"{p.name} ({p.org_name})", body=body)
    s.add(m)
    c.last_message_at = datetime.now(timezone.utc)
    s.flush()
    if p.is_pharmacy:
        c.pharmacy_last_read_id = m.id
    else:
        c.supplier_last_read_id = m.id
    s.commit()
    other = c.supplier_org_id if p.is_pharmacy else c.pharmacy_org_id
    manager.push_threadsafe(other, {"kind": "message", "conversation_id": c.id})
    manager.push_threadsafe(p.org_id, {"kind": "message", "conversation_id": c.id})
    notify(s, other, "message", f"New message from {p.org_name}", body[:200], f"/messages/{c.id}")
    return m


Trader = Annotated[Principal, require_org(OrgType.PHARMACY, OrgType.SUPPLIER)]


@app.get("/conversations", response_model=list[schemas.ConversationOut], tags=["messaging"])
def list_conversations(p: Trader, s: DB):
    return _conversations(s, p)


@app.post("/conversations", response_model=schemas.ConversationOut, status_code=201, tags=["messaging"])
def start_conversation(body: schemas.ConversationCreate, p: Trader, s: DB):
    if body.counterpart_org_id == p.org_id:
        raise HTTPException(400, "You cannot message your own organisation")
    if p.is_pharmacy:
        c = Conversation(pharmacy_org_id=p.org_id, pharmacy_name=p.org_name,
                         supplier_org_id=body.counterpart_org_id, supplier_name=body.counterpart_org_name,
                         subject=body.subject, order_number=body.order_number)
    else:
        c = Conversation(supplier_org_id=p.org_id, supplier_name=p.org_name,
                         pharmacy_org_id=body.counterpart_org_id, pharmacy_name=body.counterpart_org_name,
                         subject=body.subject, order_number=body.order_number)
    s.add(c)
    s.flush()
    _post_message(s, c, p, body.body)
    return next(x for x in _conversations(s, p) if x["id"] == c.id)


@app.get("/conversations/{cid}/messages", response_model=list[schemas.MessageOut], tags=["messaging"])
def get_messages(cid: int, p: Trader, s: DB):
    c = _get_conversation(s, cid, p)
    if c.messages:
        if p.is_pharmacy:
            c.pharmacy_last_read_id = c.messages[-1].id
        else:
            c.supplier_last_read_id = c.messages[-1].id
        s.commit()
    return c.messages


@app.post("/conversations/{cid}/messages", response_model=schemas.MessageOut, status_code=201, tags=["messaging"])
def send_message(cid: int, body: schemas.MessageCreate, p: Trader, s: DB):
    return _post_message(s, _get_conversation(s, cid, p), p, body.body)


# ---------------------------------------------------------------- broadcasts
@app.post("/broadcasts", response_model=schemas.BroadcastOut, status_code=201, tags=["broadcasts"])
def create_broadcast(body: schemas.BroadcastCreate, s: DB,
                     p: Principal = require_org(OrgType.SUPPLIER, OrgType.PLATFORM)):
    if p.is_supplier and body.audience != Audience.PHARMACIES:
        raise HTTPException(403, "Suppliers can only broadcast to pharmacies")
    b = Broadcast(sender_org_id=p.org_id, sender_org_name=p.org_name, sender_org_type=p.org_type,
                  audience=body.audience, title=body.title, body=body.body)
    s.add(b)
    s.commit()
    return b


@app.get("/broadcasts", response_model=list[schemas.BroadcastOut], tags=["broadcasts"])
def list_broadcasts(p: CurrentUser, s: DB, limit: int = Query(20, le=100)):
    audiences = [Audience.ALL]
    if p.is_pharmacy:
        audiences.append(Audience.PHARMACIES)
    elif p.is_supplier:
        audiences.append(Audience.SUPPLIERS)
    stmt = select(Broadcast).where(or_(Broadcast.audience.in_(audiences), Broadcast.sender_org_id == p.org_id))
    if p.is_platform_admin:
        stmt = select(Broadcast)
    return s.scalars(stmt.order_by(Broadcast.id.desc()).limit(limit)).all()


# ---------------------------------------------------------------- internal
@app.post("/internal/events", status_code=202, tags=["internal"], dependencies=[Depends(require_service)])
def receive_event(event: dict, s: DB):
    """Development fallback for the Redis event bus (see EVENT_WEBHOOK_URL)."""
    handle_event(s, event)
