"""Authenticated request identity shared by gateway and MCP tool handlers."""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass


@dataclass(frozen=True)
class Identity:
    actor_type: str
    actor_id: str
    role: str


current_identity: ContextVar[Identity | None] = ContextVar(
    "current_identity", default=None
)
