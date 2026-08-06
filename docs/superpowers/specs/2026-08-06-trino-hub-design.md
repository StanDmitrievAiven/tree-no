# Trino Hub Design

## Goal

Deploy a new single-node Trino hub to the active `aws-eu-west-1` project VPC. It provides federated, read-only analytics across the project ClickHouse, PostgreSQL, and Kafka services, plus an MCP interface for managed agents and a browser/SQL interface for people.

## Topology

The `trino-hub` application is a single container with three local processes:

1. Trino runs as one coordinator/worker instance.
2. A Trino MCP server exposes read-only catalog discovery and SQL tools at `/mcp`.
3. A small gateway is the only public listener. It routes `/mcp` to the MCP service and all other paths to Trino, authenticating human and MCP clients before forwarding requests.

This is a single-node federation hub, not a multi-worker MPP cluster. The initial application plan is 2 vCPU and 4 GB RAM; it can be increased if query memory pressure appears.

## Authentication and credential storage

A dedicated PostgreSQL service in the same VPC stores:

- User records with Argon2id password hashes and roles.
- MCP API-key hashes and roles.
- Encrypted Trino catalog definitions.
- Audit events for authentication and query submissions.

The gateway verifies human basic-auth credentials and MCP API keys against PostgreSQL. It passes the authenticated identity to Trino as the user. No Open Policy Agent is used. The catalog-encryption key is an Aiven application secret; connector credentials are encrypted before being written to PostgreSQL and decrypted only while producing Trino catalog files.

## Data catalogs

The initial catalogs are:

- `postgres`: `pg-37c7de3b`.
- `clickhouse`: `clickhouse-2a6274d2`.
- `kafka`: `kafka-1b5cb1e7`.

All source connectivity stays in the `aws-eu-west-1` VPC. The service never connects to DataHub infrastructure services.

## MCP behavior

The MCP server uses Streamable HTTP with standard session tracking and exposes only:

- catalog, schema, table, and column discovery;
- read-only SQL (`SELECT`, `SHOW`, `DESCRIBE`, `EXPLAIN`, and `WITH ... SELECT`);
- query timeout and result row limits.

Write statements, DDL, and data-changing operations are rejected before reaching Trino.

## Deployment

The new public Aiven Application is named `trino-hub`. A dedicated PostgreSQL service is created first and integrated with the app as `DATABASE_URL`; Aiven injects its CA certificate. The application parses that connection URL, removes `sslmode`, and validates PostgreSQL TLS using `PROJECT_CA_CERT`. The application is placed in VPC `fafac515-1f8a-4095-ae5a-6bebf583643a`.
