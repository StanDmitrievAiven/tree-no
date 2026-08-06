"""Remote Streamable HTTP MCP surface for the Trino federation hub."""

from __future__ import annotations

import re

from gateway_identity import current_identity
from gateway_repository import GatewayRepository
from trino_client import TrinoClient

from mcp.server.mcpserver import MCPServer

mcp = MCPServer("Trino Federation Hub")
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _identity():
    identity = current_identity.get()
    if identity is None:
        raise PermissionError("Gateway authentication is required")
    return identity


def _query(sql: str) -> dict:
    identity = _identity()
    result = TrinoClient().query(sql, identity.actor_id)
    GatewayRepository().audit(identity, "mcp_query", sql)
    return result


def _identifier(value: str) -> str:
    if not _IDENTIFIER.fullmatch(value):
        raise ValueError("Catalog, schema, and table names must be simple identifiers")
    return value


@mcp.tool()
def list_catalogs() -> dict:
    """List catalogs available through this read-only federation hub."""
    return _query("SHOW CATALOGS")


@mcp.tool()
def list_schemas(catalog: str) -> dict:
    """List schemas for a catalog."""
    return _query(f'SHOW SCHEMAS FROM "{_identifier(catalog)}"')


@mcp.tool()
def list_tables(catalog: str, schema: str) -> dict:
    """List tables for a catalog schema."""
    return _query(f'SHOW TABLES FROM "{_identifier(catalog)}"."{_identifier(schema)}"')


@mcp.tool()
def describe_table(catalog: str, schema: str, table: str) -> dict:
    """List columns and types for a table."""
    return _query(
        f'DESCRIBE "{_identifier(catalog)}"."{_identifier(schema)}"."{_identifier(table)}"'
    )


@mcp.tool()
def query(sql: str) -> dict:
    """Run a bounded, read-only SQL statement against Trino."""
    return _query(sql)
