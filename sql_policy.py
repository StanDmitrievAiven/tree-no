"""Conservative read-only SQL validation for MCP requests."""

from __future__ import annotations

import re


class SQLPolicyError(ValueError):
    """Raised when a query is outside the hub's read-only contract."""


_COMMENTS = re.compile(r"(?m)--[^\n]*$|/\*.*?\*/", re.DOTALL)
_TOKENS = re.compile(r"[A-Za-z_]+")
_ALLOWED_START = {"SELECT", "SHOW", "DESCRIBE", "DESC", "EXPLAIN", "WITH"}
_FORBIDDEN = {
    "ALTER",
    "CALL",
    "CREATE",
    "DELETE",
    "DROP",
    "GRANT",
    "INSERT",
    "MERGE",
    "RENAME",
    "REVOKE",
    "SET",
    "TRUNCATE",
    "UPDATE",
    "USE",
}


def _outside_quotes(sql: str) -> str:
    """Replace quoted literals/identifiers so keyword checks inspect SQL syntax."""
    output: list[str] = []
    quote: str | None = None
    index = 0
    while index < len(sql):
        character = sql[index]
        if quote:
            output.append(" ")
            if character == quote:
                if index + 1 < len(sql) and sql[index + 1] == quote:
                    output.append(" ")
                    index += 2
                    continue
                quote = None
            index += 1
            continue
        if character in {"'", '"'}:
            quote = character
            output.append(" ")
        else:
            output.append(character)
        index += 1
    if quote:
        raise SQLPolicyError("SQL contains an unterminated quoted value")
    return "".join(output)


def validate_read_only_sql(sql: str) -> str:
    """Return normalized SQL only when it is a single safe read-only statement."""
    normalized = _COMMENTS.sub("", sql).strip()
    if normalized.endswith(";"):
        normalized = normalized[:-1].rstrip()
    code = _outside_quotes(normalized)
    if not normalized or ";" in code:
        raise SQLPolicyError("SQL must contain exactly one statement")

    tokens = [token.upper() for token in _TOKENS.findall(code)]
    if not tokens or tokens[0] not in _ALLOWED_START:
        raise SQLPolicyError("Statement type is not permitted; only read-only queries are allowed")
    forbidden = next((token for token in tokens if token in _FORBIDDEN), None)
    if forbidden:
        raise SQLPolicyError(f"{forbidden} is not permitted")
    return normalized
