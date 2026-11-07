from datetime import timedelta

import bcrypt

from multistock_common.auth import encode_token

from .config import settings
from .models import User


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except ValueError:
        return False


def issue_tokens(user: User) -> dict:
    org = user.organization
    claims = {
        "sub": str(user.id),
        "org_id": org.id,
        "org_type": org.type.value,
        "org_name": org.name,
        "role": user.role.value,
        "name": user.full_name,
        "email": user.email,
    }
    access = encode_token(
        claims, settings.jwt_secret, settings.jwt_algorithm,
        timedelta(minutes=settings.access_token_minutes), "access",
    )
    refresh = encode_token(
        {"sub": str(user.id)}, settings.jwt_secret, settings.jwt_algorithm,
        timedelta(days=settings.refresh_token_days), "refresh",
    )
    return {
        "access_token": access,
        "refresh_token": refresh,
        "expires_in": settings.access_token_minutes * 60,
    }
