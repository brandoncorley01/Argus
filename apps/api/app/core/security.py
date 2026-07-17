from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import Final

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

_password_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)
DUMMY_PASSWORD_HASH: Final[str] = _password_hasher.hash("argus-timing-dummy-password")


def hash_password(password: str) -> str:
    if not password:
        raise ValueError("password must not be blank")
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Verify password. Always performs a hash operation to reduce timing variance."""
    try:
        return bool(_password_hasher.verify(password_hash, password))
    except (VerifyMismatchError, InvalidHashError):
        try:
            _password_hasher.verify(DUMMY_PASSWORD_HASH, password)
        except (VerifyMismatchError, InvalidHashError):
            pass
        return False


def generate_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def tokens_match(left: str, right: str) -> bool:
    return hmac.compare_digest(left, right)
