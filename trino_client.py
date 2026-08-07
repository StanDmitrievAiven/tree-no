"""Small bounded client for Trino's statement REST API."""

from __future__ import annotations

import os
import time
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

from sql_policy import validate_read_only_sql


class TrinoQueryError(RuntimeError):
    """A sanitized Trino execution error."""


class TrinoClient:
    def __init__(self) -> None:
        self._base_url = os.environ.get("TRINO_INTERNAL_URL", "http://127.0.0.1:8080")
        self._service_user = os.environ["TRINO_SERVICE_USER"]
        self._service_password = os.environ["TRINO_SERVICE_PASSWORD"]
        self._timeout_seconds = float(os.environ.get("TRINO_MCP_QUERY_TIMEOUT_SECONDS", "30"))
        self._row_limit = int(os.environ.get("TRINO_MCP_MAX_ROWS", "1000"))

    def query(self, sql: str, user: str) -> dict[str, Any]:
        statement = validate_read_only_sql(sql)
        headers = {
            # Trino password authentication requires the requested user to match
            # the Basic-auth principal. The gateway retains `user` in its audit
            # database rather than forwarding a conflicting identity upstream.
            "X-Trino-User": self._service_user,
            "X-Trino-Source": "trino-hub-mcp",
            # Trino's password authenticator requires HTTPS. The gateway
            # terminates TLS at the public edge and Trino trusts this marker.
            "X-Forwarded-Proto": "https",
        }
        deadline = time.monotonic() + self._timeout_seconds
        with httpx.Client(
            auth=(self._service_user, self._service_password),
            timeout=min(self._timeout_seconds, 10),
        ) as client:
            response = client.post(
                f"{self._base_url}/v1/statement",
                content=statement,
                headers=headers,
            )
            return self._consume_response(client, response, deadline)

    def _consume_response(
        self, client: httpx.Client, response: httpx.Response, deadline: float
    ) -> dict[str, Any]:
        columns: list[str] = []
        rows: list[list[Any]] = []
        query_id: str | None = None
        while True:
            if time.monotonic() > deadline:
                self._cancel(client, response)
                raise TrinoQueryError("Query exceeded the configured timeout")
            if response.status_code >= 400:
                raise TrinoQueryError("Trino rejected the query")
            payload = response.json()
            query_id = payload.get("id", query_id)
            if payload.get("error"):
                raise TrinoQueryError("Trino could not execute the query")
            if payload.get("columns"):
                columns = [column["name"] for column in payload["columns"]]
            rows.extend(payload.get("data", []))
            if len(rows) >= self._row_limit:
                self._cancel_url(client, payload.get("nextUri"))
                rows = rows[: self._row_limit]
                break
            next_uri = payload.get("nextUri")
            if not next_uri:
                break
            response = client.get(self._internal_uri(next_uri))
        return {
            "query_id": query_id,
            "columns": columns,
            "rows": rows,
            "row_limit": self._row_limit,
            "truncated": len(rows) >= self._row_limit,
        }

    def _internal_uri(self, uri: str) -> str:
        """Keep Trino polling traffic on the local plaintext listener.

        `X-Forwarded-Proto: https` is required for password authentication, but
        it also makes Trino emit HTTPS polling URLs. TLS ends at the public
        gateway; the internal Trino listener is HTTP only.
        """
        internal = urlsplit(self._base_url)
        requested = urlsplit(uri)
        return urlunsplit(
            (internal.scheme, internal.netloc, requested.path, requested.query, "")
        )

    def _cancel(self, client: httpx.Client, response: httpx.Response) -> None:
        try:
            payload = response.json()
            self._cancel_url(client, payload.get("nextUri"))
        except (ValueError, httpx.HTTPError):
            return

    def _cancel_url(self, client: httpx.Client, next_uri: str | None) -> None:
        if next_uri:
            try:
                client.delete(self._internal_uri(next_uri))
            except httpx.HTTPError:
                pass
