import base64
import hashlib
import secrets
import time
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from ttc.core.config import get_settings

_hasher = PasswordHasher()


def uuid7() -> UUID:
    timestamp_ms = time.time_ns() // 1_000_000
    value = (timestamp_ms << 80) | (7 << 76) | (secrets.randbits(12) << 64)
    return UUID(int=value | (2 << 62) | secrets.randbits(62))


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        return _hasher.verify(stored_hash, password)
    except VerificationError:
        return False


def _jwt_secret() -> str:
    secret = get_settings().jwt_secret
    if not secret or len(secret.encode()) < 32:
        raise RuntimeError("JWT_SECRET must contain at least 32 bytes")
    return secret


def access_token(user_id: UUID) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {"sub": str(user_id), "iss": "ttc-api", "aud": "ttc-api", "iat": now,
         "exp": now + timedelta(minutes=15)},
        _jwt_secret(), algorithm="HS256",
    )


def decode_access_token(token: str) -> UUID:
    data = jwt.decode(token, _jwt_secret(), algorithms=["HS256"],
                      issuer="ttc-api", audience="ttc-api", options={"require": ["exp", "sub"]})
    return UUID(data["sub"])


def new_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def token_digest(token: str) -> bytes:
    return hashlib.sha256(token.encode()).digest()


def encrypt_contact(value: str) -> bytes:
    encoded = get_settings().column_encryption_key
    if not encoded:
        raise RuntimeError("COLUMN_ENCRYPTION_KEY must be configured")
    key = base64.urlsafe_b64decode(encoded)
    if len(key) != 32:
        raise RuntimeError("COLUMN_ENCRYPTION_KEY must decode to 32 bytes")
    nonce = secrets.token_bytes(12)
    return nonce + AESGCM(key).encrypt(nonce, value.encode(), None)
