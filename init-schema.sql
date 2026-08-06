-- Trino catalog store: persists connector config across restarts
CREATE TABLE IF NOT EXISTS trino_catalogs (
  id SERIAL PRIMARY KEY,
  name VARCHAR(255) UNIQUE NOT NULL,
  properties JSONB NOT NULL CHECK (
    properties ? '_encrypted' AND (properties->>'_encrypted')::boolean = true
  ),
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Kafka client config (SASL_SSL etc.) - written to /etc/trino/kafka-client.properties
CREATE TABLE IF NOT EXISTS trino_kafka_config (
  id SERIAL PRIMARY KEY,
  config_text JSONB NOT NULL CHECK (
    config_text ? '_encrypted' AND (config_text->>'_encrypted')::boolean = true
  ),
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS trino_users (
 id UUID PRIMARY KEY,
 username VARCHAR(255) UNIQUE NOT NULL,
 password_hash TEXT NOT NULL CHECK (password_hash LIKE '$argon2id$%'),
 role VARCHAR(32) NOT NULL CHECK (role IN ('admin', 'analyst', 'viewer')),
 enabled BOOLEAN NOT NULL DEFAULT true,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS trino_mcp_api_keys (
 id UUID PRIMARY KEY,
 name VARCHAR(255) UNIQUE NOT NULL,
 key_hash TEXT NOT NULL CHECK (key_hash LIKE '$argon2id$%'),
 role VARCHAR(32) NOT NULL CHECK (role IN ('admin', 'analyst', 'viewer')),
 enabled BOOLEAN NOT NULL DEFAULT true,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 revoked_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS trino_audit_events (
 id BIGSERIAL PRIMARY KEY,
 actor_type VARCHAR(16) NOT NULL CHECK (actor_type IN ('user', 'mcp')),
 actor_id VARCHAR(255) NOT NULL,
 action VARCHAR(64) NOT NULL,
 query_hash TEXT,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS trino_audit_events_created_at_idx
  ON trino_audit_events (created_at DESC);
