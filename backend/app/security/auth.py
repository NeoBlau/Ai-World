"""Password hashing (scrypt) and JWT tokens for human users."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import uuid
from datetime import timedelta

import jwt

from app.core.config import get_settings
from app.core.time import utcnow

_N, _R, _P = 2**14, 8, 1


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(dk).decode()


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, salt_b64, dk_b64 = stored.split("$")
    except ValueError:
        return False
    if algo != "scrypt":
        return False
    salt, expected = base64.b64decode(salt_b64), base64.b64decode(dk_b64)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=len(expected))
    return hmac.compare_digest(dk, expected)


def create_token(user_id: uuid.UUID, role: str) -> str:
    s = get_settings()
    now = utcnow()
    payload = {"sub": str(user_id), "role": role, "iat": now, "exp": now + timedelta(minutes=s.jwt_expire_minutes)}
    return jwt.encode(payload, s.jwt_secret.get_secret_value(), algorithm="HS256")


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, get_settings().jwt_secret.get_secret_value(), algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
