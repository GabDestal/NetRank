"""API-key protection for administrative endpoints (decision log D44)."""

import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader

from app.config import get_settings

API_KEY_HEADER = "X-API-Key"

_header = APIKeyHeader(
    name=API_KEY_HEADER, auto_error=False, description="Admin key (ADMIN_API_KEY on the server)."
)


def require_admin_key(provided: Annotated[str | None, Depends(_header)]) -> None:
    """401 without a key, 403 with a wrong key, 503 when the server has no key configured.

    The comparison is constant-time (secrets.compare_digest) so response timing does not reveal
    how many leading characters of a guess were right.
    """
    expected = get_settings().admin_api_key
    if expected is None or not expected.get_secret_value():
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Admin endpoints are disabled: ADMIN_API_KEY is not set"
        )
    if not provided:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            f"Missing {API_KEY_HEADER} header",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    if not secrets.compare_digest(provided.encode(), expected.get_secret_value().encode()):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid API key")


ADMIN_ONLY = Depends(require_admin_key)
