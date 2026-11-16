"""Login tokens: HMAC-SHA256 over "user:expiry", keyed with SECRET_KEY (contracts/api.md).

Token format: base64url("user:expiry") + "." + hex HMAC of that payload.
The payload is base64-encoded so a username with odd characters cannot
break the "." separator.
"""

import base64
import hashlib
import hmac
import time


def _sign(secret_key: str, payload: bytes) -> str:
    return hmac.new(secret_key.encode(), payload, hashlib.sha256).hexdigest()


def make_token(secret_key: str, username: str, ttl_seconds: int, now: float | None = None) -> str:
    now = time.time() if now is None else now
    expiry = int(now) + ttl_seconds
    payload = f"{username}:{expiry}".encode()
    encoded = base64.urlsafe_b64encode(payload).decode().rstrip("=")
    return f"{encoded}.{_sign(secret_key, payload)}"


def verify_token(secret_key: str, token: str, now: float | None = None) -> str | None:
    """Return the username if the token is genuine and not expired, else None."""
    now = time.time() if now is None else now
    try:
        encoded, signature = token.split(".", 1)
        payload = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
        username, expiry = payload.decode().rsplit(":", 1)
        expiry_ts = int(expiry)
    except ValueError:  # bad split, bad base64, bad utf-8 and bad int are all ValueError
        return None
    # compare_digest: constant-time, so the signature cannot be guessed byte by byte.
    if not hmac.compare_digest(signature, _sign(secret_key, payload)):
        return None
    if expiry_ts < now:
        return None
    return username
