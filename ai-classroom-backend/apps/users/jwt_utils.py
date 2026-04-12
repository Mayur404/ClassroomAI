from datetime import datetime, timedelta, timezone

import jwt
from django.conf import settings


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _jwt_secret() -> str:
    return settings.SECRET_KEY


def _base_payload(user, token_type: str, minutes: int) -> dict:
    issued_at = _now_utc()
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "role": user.role,
        "type": token_type,
        "iat": int(issued_at.timestamp()),
    }
    if not getattr(settings, "JWT_NEVER_EXPIRES", False):
        expires_at = issued_at + timedelta(minutes=minutes)
        payload["exp"] = int(expires_at.timestamp())
    return payload


def issue_access_token(user) -> str:
    payload = _base_payload(user, token_type="access", minutes=settings.JWT_ACCESS_TOKEN_MINUTES)
    return jwt.encode(payload, _jwt_secret(), algorithm="HS256")


def issue_refresh_token(user) -> str:
    payload = _base_payload(user, token_type="refresh", minutes=settings.JWT_REFRESH_TOKEN_MINUTES)
    return jwt.encode(payload, _jwt_secret(), algorithm="HS256")


def decode_token(token: str) -> dict:
    return jwt.decode(token, _jwt_secret(), algorithms=["HS256"])
