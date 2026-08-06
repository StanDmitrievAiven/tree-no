"""PostgreSQL-backed user, API-key, and audit storage for the gateway."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from gateway_identity import Identity
from pg_connect import connect_pg

_HASHER = PasswordHasher()


@dataclass(frozen=True)
class StoredPrincipal:
    name: str
    secret_hash: str
    role: str


class GatewayRepository:
    """Encapsulates gateway database access; secrets are never logged or returned."""

    def _fetch_principal(self, query: str, name: str) -> StoredPrincipal | None:
        connection = connect_pg()
        try:
            with connection.cursor() as cursor:
                cursor.execute(query, (name,))
                row = cursor.fetchone()
            return StoredPrincipal(*row) if row else None
        finally:
            connection.close()

    def authenticate_user(self, username: str, password: str) -> Identity | None:
        principal = self._fetch_principal(
            """
            SELECT username, password_hash, role
            FROM trino_users
            WHERE username = %s AND enabled = true
            """,
            username,
        )
        if not principal or not _verify_hash(principal.secret_hash, password):
            return None
        return Identity("user", principal.name, principal.role)

    def authenticate_mcp_key(self, api_key: str) -> Identity | None:
        # Key IDs are intentionally not exposed to clients. Every active hash is
        # checked using Argon2id to support independently generated API keys.
        connection = connect_pg()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT name, key_hash, role
                    FROM trino_mcp_api_keys
                    WHERE enabled = true AND revoked_at IS NULL
                    """
                )
                rows = cursor.fetchall()
        finally:
            connection.close()
        for name, key_hash, role in rows:
            if _verify_hash(key_hash, api_key):
                return Identity("mcp", name, role)
        return None

    def audit(self, identity: Identity, action: str, query: str | None = None) -> None:
        query_hash = hashlib.sha256(query.encode()).hexdigest() if query else None
        connection = connect_pg()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO trino_audit_events (actor_type, actor_id, action, query_hash)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (identity.actor_type, identity.actor_id, action, query_hash),
                )
            connection.commit()
        finally:
            connection.close()


def _verify_hash(encoded_hash: str, value: str) -> bool:
    try:
        return _HASHER.verify(encoded_hash, value)
    except (InvalidHashError, VerificationError, VerifyMismatchError):
        return False
