from datetime import datetime, timedelta, timezone

import jwt
from django.conf import settings


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _jwt_secret() -> str:
    return settings.SECRET_KEY


def _base_payload(user, token_type: str, minutes: int) -> dict:
    issued_at = _now_utc()
    expires_at = issued_at + timedelta(minutes=minutes)
    return {
        "sub": str(user.id),
        "email": user.email,
        "role": user.role,
        "type": token_type,
        "iat": int(issued_at.timestamp()),
        "exp": int(expires_at.timestamp()),
    }


def issue_access_token(user) -> str:
    payload = _base_payload(user, token_type="access", minutes=15)
    return jwt.encode(payload, _jwt_secret(), algorithm="HS256")


def issue_refresh_token(user) -> str:
    payload = _base_payload(user, token_type="refresh", minutes=60 * 24 * 7)
    return jwt.encode(payload, _jwt_secret(), algorithm="HS256")


def decode_token(token: str) -> dict:
    return jwt.decode(token, _jwt_secret(), algorithms=["HS256"])
