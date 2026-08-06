"""Authenticated ASGI gateway for Trino's UI/API and the MCP endpoint."""

from __future__ import annotations

import base64
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.routing import Mount

from gateway_identity import current_identity
from gateway_repository import GatewayRepository
from gateway_security import AuthenticationError, extract_mcp_api_key, require_runtime_secrets
from trino_mcp import mcp

_HOP_BY_HOP = {
    "connection",
    "content-length",
    "host",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}


def _basic_credentials(header: str) -> tuple[str, str]:
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "basic" or not token:
        raise AuthenticationError("Human access requires HTTP Basic authentication")
    try:
        username, password = base64.b64decode(token, validate=True).decode().split(":", 1)
    except (UnicodeDecodeError, ValueError):
        raise AuthenticationError("Malformed HTTP Basic authentication") from None
    if not username or not password:
        raise AuthenticationError("Human access requires a username and password")
    return username, password


class GatewayAuthenticationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path == "/health":
            return await call_next(request)
        repository = GatewayRepository()
        try:
            if request.url.path.startswith("/mcp"):
                identity = repository.authenticate_mcp_key(
                    extract_mcp_api_key(request.headers)
                )
            else:
                username, password = _basic_credentials(
                    request.headers.get("authorization", "")
                )
                identity = repository.authenticate_user(username, password)
            if identity is None:
                raise AuthenticationError("Invalid credentials")
        except AuthenticationError as error:
            return JSONResponse(
                {"detail": str(error)},
                status_code=401,
                headers={"WWW-Authenticate": "Basic realm=trino-hub"},
            )
        token = current_identity.set(identity)
        try:
            repository.audit(identity, "authentication")
            return await call_next(request)
        finally:
            current_identity.reset(token)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    require_runtime_secrets(os.environ)
    async with mcp.session_manager.run():
        yield


app = FastAPI(lifespan=lifespan)
app.add_middleware(GatewayAuthenticationMiddleware)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


async def proxy_to_trino(request: Request, path: str = "") -> Response:
    """Forward UI and SQL-protocol requests only after database authentication."""
    identity = current_identity.get()
    if identity is None:
        return JSONResponse({"detail": "Unauthorized"}, status_code=401)
    headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower() not in _HOP_BY_HOP | {"authorization"}
    }
    headers["X-Trino-User"] = identity.actor_id
    headers["X-Forwarded-Proto"] = "https"
    headers["X-Forwarded-For"] = request.client.host if request.client else "unknown"
    upstream = os.environ.get("TRINO_INTERNAL_URL", "http://127.0.0.1:8080")
    target = f"{upstream.rstrip('/')}/{path}"
    if request.url.query:
        target = f"{target}?{request.url.query}"
    body = await request.body()
    async with httpx.AsyncClient(
        auth=(os.environ["TRINO_SERVICE_USER"], os.environ["TRINO_SERVICE_PASSWORD"]),
        timeout=float(os.environ.get("TRINO_PROXY_TIMEOUT_SECONDS", "60")),
    ) as client:
        response = await client.request(
            request.method, target, content=body, headers=headers
        )
    response_headers = {
        key: value
        for key, value in response.headers.items()
        if key.lower() not in _HOP_BY_HOP
    }
    return Response(
        content=response.content,
        status_code=response.status_code,
        headers=response_headers,
        media_type=response.headers.get("content-type"),
    )


app.mount(
    "/mcp",
    mcp.streamable_http_app(
        streamable_http_path="/", json_response=True, host="0.0.0.0"
    ),
)
app.add_api_route("/{path:path}", proxy_to_trino, methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
