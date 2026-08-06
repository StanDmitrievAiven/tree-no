#!/usr/bin/env python3
"""
Encrypt PostgreSQL and ClickHouse connector credentials and upsert into trino-hub-pg.

No Aiven service integrations required — credentials live in PG, encrypted at rest.

Usage (one-time or on credential rotation):
  export TRINO_CATALOG_ENCRYPTION_KEY='...'   # same secret as on trino2 app
  export DATABASE_URL='postgresql://...'    # trino2-pg connection
  export SUMMIT_PG_PASSWORD='...'
  export CLICKHOUSE_USER='avnadmin'
  export CLICKHOUSE_PASSWORD='...'
  python3 store_encrypted_catalogs.py

Or from trino2 entrypoint when credential env vars are set (see entrypoint.sh).
"""
from __future__ import annotations

import json
import os
import sys

from catalog_crypto import encrypt_payload, require_encryption_key
from pg_connect import connect_pg

# VPC hostnames for the project data services.
SUMMIT_PG_HOST = "pg-37c7de3b-data-innovation-summit.c.aivencloud.com"
SUMMIT_PG_PORT = 14208
CLICKHOUSE_HOST = "clickhouse-2a6274d2-data-innovation-summit.c.aivencloud.com"
CLICKHOUSE_PORT = 14209

CATALOGS: list[tuple[str, dict[str, str]]] = [
    (
        "summit_pg",
        {
            "connector.name": "postgresql",
            "connection-url": (
                f"jdbc:postgresql://{SUMMIT_PG_HOST}:{SUMMIT_PG_PORT}/defaultdb?sslmode=require"
            ),
            "connection-user": "avnadmin",
            "connection-password": "",  # filled from env
        },
    ),
    (
        "summit_clickhouse",
        {
            "connector.name": "clickhouse",
            "connection-url": (
                f"jdbc:clickhouse://{CLICKHOUSE_HOST}:{CLICKHOUSE_PORT}/default?ssl=true"
            ),
            "connection-user": "",  # filled from env
            "connection-password": "",  # filled from env
        },
    ),
]

INIT_SCHEMA = """
CREATE TABLE IF NOT EXISTS trino_catalogs (
  id SERIAL PRIMARY KEY,
  name VARCHAR(255) UNIQUE NOT NULL,
  properties JSONB NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
"""


def _build_catalogs_from_env() -> list[tuple[str, dict[str, str]]]:
    pg_password = os.environ.get("SUMMIT_PG_PASSWORD", "").strip()
    ch_user = os.environ.get("CLICKHOUSE_USER", "avnadmin").strip()
    ch_password = os.environ.get("CLICKHOUSE_PASSWORD", "").strip()

    if not pg_password and not ch_password:
        return []

    out: list[tuple[str, dict[str, str]]] = []
    for name, props in CATALOGS:
        props = dict(props)
        if name == "summit_pg":
            if not pg_password:
                continue
            props["connection-password"] = pg_password
        elif name == "summit_clickhouse":
            if not ch_password:
                continue
            props["connection-user"] = ch_user
            props["connection-password"] = ch_password
        out.append((name, props))
    return out


def store_catalogs(catalogs: list[tuple[str, dict[str, str]]], key: str) -> None:
    conn = connect_pg()
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(INIT_SCHEMA)
            cur.execute("DELETE FROM trino_catalogs WHERE name = 'summit_kafka'")
            cur.execute("DROP TABLE IF EXISTS trino_kafka_config")
            for name, props in catalogs:
                encrypted = encrypt_payload(props, key)
                cur.execute(
                    """
                    INSERT INTO trino_catalogs (name, properties)
                    VALUES (%s, %s::jsonb)
                    ON CONFLICT (name) DO UPDATE SET properties = EXCLUDED.properties
                    """,
                    (name, json.dumps(encrypted)),
                )
                print(f"  Stored encrypted catalog: {name}")

    finally:
        conn.close()


def main() -> int:
    try:
        key = require_encryption_key()
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    catalogs = _build_catalogs_from_env()
    if not catalogs:
        print(
            "Nothing to store — set SUMMIT_PG_PASSWORD and/or CLICKHOUSE_PASSWORD.",
            file=sys.stderr,
        )
        return 1

    print("Encrypting and storing summit connector credentials in trino_catalogs...")
    store_catalogs(catalogs, key)
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
