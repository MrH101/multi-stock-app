"""Token verification shared by all services.

Only the identity service *issues* tokens; every other service just verifies them
locally with the shared secret, so no network hop is needed per request.
"""
import hmac
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Annotated

import jwt
from fastapi import Depends, Header, HTTPException, Request, status


class OrgType(StrEnum):
    PHARMACY = "PHARMACY"
    SUPPLIER = "SUPPLIER"
    PLATFORM = "PLATFORM"


class Role(StrEnum):
    OWNER = "OWNER"  # manages the organisation and its users
    MANAGER = "MANAGER"  # can do everything except manage users
    STAFF = "STAFF"  # day-to-day work: ordering / fulfilment


@dataclass(frozen=True)
class Principal:
    user_id: int
    org_id: int
    org_type: OrgType
    org_name: str
    role: Role
    name: str
    email: str

    @property
    def is_pharmacy(self) -> bool:
        return self.org_type == OrgType.PHARMACY

    @property
    def is_supplier(self) -> bool:
        return self.org_type == OrgType.SUPPLIER

    @property
    def is_platform_admin(self) -> bool:
        return self.org_type == OrgType.PLATFORM


def encode_token(claims: dict, secret: str, algorithm: str, ttl: timedelta, token_type: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {**claims, "type": token_type, "iat": now, "exp": now + ttl}
    return jwt.encode(payload, secret, algorithm=algorithm)


def decode_token(token: str, secret: str, algorithm: str, expected_type: str = "access") -> dict:
    try:
        payload = jwt.decode(token, secret, algorithms=[algorithm])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired, please sign in again")
    except jwt.InvalidTokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    if payload.get("type") != expected_type:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token type")
    return payload


def principal_from_claims(payload: dict) -> Principal:
    return Principal(
        user_id=int(payload["sub"]),
        org_id=int(payload["org_id"]),
        org_type=OrgType(payload["org_type"]),
        org_name=payload.get("org_name", ""),
        role=Role(payload["role"]),
        name=payload.get("name", ""),
        email=payload.get("email", ""),
    )


def get_principal(request: Request, authorization: Annotated[str | None, Header()] = None) -> Principal:
    settings = request.app.state.settings
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    payload = decode_token(authorization[7:], settings.jwt_secret, settings.jwt_algorithm)
    return principal_from_claims(payload)


CurrentUser = Annotated[Principal, Depends(get_principal)]


def require_org(*org_types: OrgType):
    def dependency(principal: CurrentUser) -> Principal:
        if principal.org_type not in org_types:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "This action is not available for your account type")
        return principal

    return Depends(dependency)


def require_role(*roles: Role):
    def dependency(principal: CurrentUser) -> Principal:
        if principal.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not have permission to do this")
        return principal

    return Depends(dependency)


def require_service(request: Request, x_service_token: Annotated[str | None, Header()] = None) -> None:
    expected = request.app.state.settings.service_token
    if not x_service_token or not hmac.compare_digest(x_service_token.encode(), expected.encode()):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Internal endpoint")
