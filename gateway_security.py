"""Authentication helpers and mandatory runtime-secret validation."""

from __future__ import annotations

from collections.abc import Mapping


class AuthenticationError(ValueError):
    """Raised when a request does not provide valid gateway credentials."""


_REQUIRED_SECRETS = (
    "DATABASE_URL",
    "TRINO_CATALOG_ENCRYPTION_KEY",
    "TRINO_SERVICE_USER",
    "TRINO_SERVICE_PASSWORD",
)


def require_runtime_secrets(environment: Mapping[str, str]) -> None:
    """Fail closed when a deployment has not supplied its required secrets."""
    for name in _REQUIRED_SECRETS:
        if not environment.get(name, "").strip():
            raise ValueError(f"{name} must be supplied as an application secret")


def extract_mcp_api_key(headers: Mapping[str, str]) -> str:
    """Extract an MCP key without accepting human Basic-auth credentials."""
    api_key = headers.get("x-api-key", "").strip()
    if api_key:
        return api_key
    authorization = headers.get("authorization", "")
    scheme, _, value = authorization.partition(" ")
    if scheme.lower() == "bearer" and value.strip():
        return value.strip()
    raise AuthenticationError("MCP authentication requires X-API-Key or Bearer token")
