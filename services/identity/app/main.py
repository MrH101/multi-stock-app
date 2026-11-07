from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from multistock_common.app import create_app
from multistock_common.auth import (CurrentUser, OrgType, Principal, Role, decode_token, require_org, require_role,
                                    require_service)
from multistock_common.db import Database
from multistock_common.events import EventPublisher

from . import schemas
from .config import settings
from .models import Organization, User
from .security import hash_password, issue_tokens, verify_password

db = Database(settings.database_url)
events = EventPublisher(settings.redis_url, settings.event_stream, "identity",
                        settings.event_webhook_url, settings.service_token)


def seed_admin() -> None:
    with db.SessionLocal() as s:
        if s.scalar(select(Organization).where(Organization.type == OrgType.PLATFORM)):
            return
        org = Organization(name="Multi-Stock Platform", type=OrgType.PLATFORM, verified=True)
        s.add(org)
        s.flush()
        s.add(User(org_id=org.id, email=settings.admin_email, full_name="Platform Admin",
                   password_hash=hash_password(settings.admin_password), role=Role.OWNER))
        s.commit()


@asynccontextmanager
async def lifespan(_app):
    db.create_all()
    seed_admin()
    yield


app = create_app(settings, "Identity Service")
app.router.lifespan_context = lifespan
DB = Annotated[Session, Depends(db.session)]


def _session_out(user: User) -> dict:
    return {**issue_tokens(user), "user": user, "organization": user.organization}


# ---------------------------------------------------------------- auth
@app.post("/auth/register", response_model=schemas.SessionOut, status_code=201, tags=["auth"])
def register(body: schemas.RegisterRequest, s: DB):
    if body.org_type == OrgType.PLATFORM:
        raise HTTPException(400, "Choose either Pharmacy or Supplier")
    email = body.email.lower()
    if s.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "An account with this email already exists")
    if s.scalar(select(Organization).where(Organization.license_number == body.license_number)):
        raise HTTPException(409, "This licence number is already registered")
    org = Organization(
        name=body.org_name, type=body.org_type, license_number=body.license_number,
        email=email, phone=body.org_phone, address=body.address, city=body.city,
    )
    s.add(org)
    s.flush()
    user = User(org_id=org.id, email=email, full_name=body.full_name,
                password_hash=hash_password(body.password), role=Role.OWNER)
    s.add(user)
    s.commit()
    s.refresh(user)
    events.publish("organization.registered", {"org_id": org.id, "org_type": org.type, "name": org.name})
    return _session_out(user)


@app.post("/auth/login", response_model=schemas.SessionOut, tags=["auth"])
def login(body: schemas.LoginRequest, s: DB):
    user = s.scalar(select(User).where(User.email == body.email.lower()))
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")
    if not user.is_active or not user.organization.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This account has been deactivated")
    return _session_out(user)


@app.post("/auth/refresh", response_model=schemas.SessionOut, tags=["auth"])
def refresh(body: schemas.RefreshRequest, s: DB):
    payload = decode_token(body.refresh_token, settings.jwt_secret, settings.jwt_algorithm, "refresh")
    user = s.get(User, int(payload["sub"]))
    if not user or not user.is_active or not user.organization.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session no longer valid")
    return _session_out(user)


@app.get("/me", response_model=schemas.MeOut, tags=["auth"])
def me(p: CurrentUser, s: DB):
    user = s.get(User, p.user_id)
    if not user:
        raise HTTPException(404, "User not found")
    return {"user": user, "organization": user.organization}


@app.post("/me/password", status_code=204, tags=["auth"])
def change_password(body: schemas.PasswordChange, p: CurrentUser, s: DB):
    user = s.get(User, p.user_id)
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(400, "Current password is incorrect")
    user.password_hash = hash_password(body.new_password)
    s.commit()


# ---------------------------------------------------------------- organisation
@app.get("/organizations/me", response_model=schemas.OrganizationOut, tags=["organizations"])
def my_org(p: CurrentUser, s: DB):
    return s.get(Organization, p.org_id)


@app.patch("/organizations/me", response_model=schemas.OrganizationOut, tags=["organizations"])
def update_my_org(body: schemas.OrganizationUpdate, s: DB,
                  p: Principal = require_role(Role.OWNER, Role.MANAGER)):
    org = s.get(Organization, p.org_id)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(org, k, v)
    s.commit()
    return org


@app.get("/organizations", response_model=list[schemas.OrganizationOut], tags=["organizations"])
def list_orgs(p: CurrentUser, s: DB, type: OrgType | None = None, q: str | None = None,
              limit: int = Query(100, le=500)):
    stmt = select(Organization).where(Organization.type != OrgType.PLATFORM)
    if not p.is_platform_admin:
        # Pharmacies browse suppliers and suppliers see pharmacies; only active ones.
        stmt = stmt.where(Organization.is_active.is_(True))
    if type:
        stmt = stmt.where(Organization.type == type)
    if q:
        stmt = stmt.where(func.lower(Organization.name).contains(q.lower()))
    return s.scalars(stmt.order_by(Organization.name).limit(limit)).all()


@app.get("/organizations/{org_id}", response_model=schemas.OrganizationOut, tags=["organizations"])
def get_org(org_id: int, _p: CurrentUser, s: DB):
    org = s.get(Organization, org_id)
    if not org:
        raise HTTPException(404, "Organisation not found")
    return org


@app.patch("/admin/organizations/{org_id}", response_model=schemas.OrganizationOut, tags=["admin"])
def admin_update_org(org_id: int, body: schemas.AdminOrganizationUpdate, s: DB,
                     _p: Principal = require_org(OrgType.PLATFORM)):
    org = s.get(Organization, org_id)
    if not org:
        raise HTTPException(404, "Organisation not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(org, k, v)
    s.commit()
    events.publish("organization.updated", {"org_id": org.id, "verified": org.verified, "is_active": org.is_active})
    return org


# ---------------------------------------------------------------- team
@app.get("/users", response_model=list[schemas.UserOut], tags=["team"])
def list_team(p: CurrentUser, s: DB):
    return s.scalars(select(User).where(User.org_id == p.org_id).order_by(User.full_name)).all()


@app.post("/users", response_model=schemas.UserOut, status_code=201, tags=["team"])
def add_team_member(body: schemas.UserCreate, s: DB, p: Principal = require_role(Role.OWNER)):
    email = body.email.lower()
    if s.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "An account with this email already exists")
    user = User(org_id=p.org_id, email=email, full_name=body.full_name, phone=body.phone,
                role=body.role, password_hash=hash_password(body.password))
    s.add(user)
    s.commit()
    return user


@app.patch("/users/{user_id}", response_model=schemas.UserOut, tags=["team"])
def update_team_member(user_id: int, body: schemas.UserUpdate, s: DB, p: Principal = require_role(Role.OWNER)):
    user = s.get(User, user_id)
    if not user or user.org_id != p.org_id:
        raise HTTPException(404, "User not found")
    changes = body.model_dump(exclude_unset=True)
    if user.id == p.user_id and (changes.get("is_active") is False or changes.get("role", Role.OWNER) != Role.OWNER):
        raise HTTPException(400, "You cannot deactivate or demote yourself")
    for k, v in changes.items():
        setattr(user, k, v)
    s.commit()
    return user


# ---------------------------------------------------------------- internal (monitoring agent)
@app.get("/internal/organizations", tags=["internal"], dependencies=[Depends(require_service)])
def internal_organizations(s: DB):
    """Directory snapshot for the monitoring agent: who exists, what type, and whether active."""
    return [{"id": o.id, "name": o.name, "type": o.type, "is_active": o.is_active, "verified": o.verified}
            for o in s.scalars(select(Organization).order_by(Organization.id))]
