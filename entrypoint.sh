#!/bin/sh
set -e

cd /opt/trino-init

# --- Environment Variable Check ---
# Support DATABASE_URL (Aiven) or TRINO_CATALOG_DB_URL
CATALOG_DB_URL="${TRINO_CATALOG_DB_URL:-$DATABASE_URL}"
if [ -z "$CATALOG_DB_URL" ]; then
    echo "ERROR: Database connection required. Set either:"
    echo "  - DATABASE_URL (auto-set when connecting PostgreSQL in Aiven)"
    echo "  - TRINO_CATALOG_DB_URL (for a separate catalog store)"
    exit 1
fi
echo "Using catalog database."
echo "---"

# --- Required deployment secrets ---
: "${TRINO_SERVICE_USER:?TRINO_SERVICE_USER must be supplied as an application secret}"
: "${TRINO_SERVICE_PASSWORD:?TRINO_SERVICE_PASSWORD must be supplied as an application secret}"
: "${TRINO_INTERNAL_SECRET:?TRINO_INTERNAL_SECRET must be supplied as an application secret}"
: "${TRINO_CATALOG_ENCRYPTION_KEY:?TRINO_CATALOG_ENCRYPTION_KEY must be supplied as an application secret}"
: "${SUMMIT_PG_PASSWORD:?SUMMIT_PG_PASSWORD must be supplied as an application secret}"
: "${CLICKHOUSE_PASSWORD:?CLICKHOUSE_PASSWORD must be supplied as an application secret}"

# --- Password authentication ---
echo "Configuring password authentication for gateway service account."
python3 /opt/trino-init/init_password_auth.py
echo "---"

# --- Initialize schema and fetch catalogs from PG ---
echo "Initializing hub schema and encrypted catalogs..."
python3 /opt/trino-init/seed_catalogs.py
python3 /opt/trino-init/store_encrypted_catalogs.py
python3 /opt/trino-init/fetch_catalogs.py
chown -R trino:trino /etc/trino/catalog 2>/dev/null || true
echo "Catalogs synced."
echo "---"

# --- Port configuration ---
TRINO_PORT="${TRINO_INTERNAL_PORT:-8080}"
GATEWAY_PORT="${PORT:-3000}"

# --- Enable dynamic catalog management (add catalogs without restart) ---
CONFIG_FILE="/etc/trino/config.properties"
if [ -f "$CONFIG_FILE" ] && ! grep -q "catalog.management" "$CONFIG_FILE"; then
    echo "catalog.management=dynamic" >> "$CONFIG_FILE"
    echo "Enabled dynamic catalog management."
fi

# --- Start Trino in background ---
echo "Starting Trino..."
/usr/lib/trino/bin/launcher run --etc-dir /etc/trino -Dnode.id=trino &
TRINO_PID=$!

# --- Wait for Trino to be ready ---
echo "Waiting for Trino to be ready..."
for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do
    if curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:${TRINO_PORT}/v1/status" 2>/dev/null | grep -q "200"; then
        echo "Trino is ready."
        break
    fi
    sleep 2
done

# --- Start catalog watcher (polls PG, runs CREATE CATALOG for new connectors) ---
export TRINO_INTERNAL_URL="http://127.0.0.1:${TRINO_PORT}"
echo -n "$TRINO_SERVICE_PASSWORD" > /tmp/trino-watcher-password
chmod 600 /tmp/trino-watcher-password
export TRINO_ADMIN_USER="$TRINO_SERVICE_USER"
export TRINO_ADMIN_PASSWORD_FILE=/tmp/trino-watcher-password
python3 /opt/trino-init/catalog_watcher.py &
WATCHER_PID=$!

# --- Start the only public listener: authenticated gateway ---
echo "Starting authenticated gateway on port ${GATEWAY_PORT}..."
python3 -m uvicorn gateway:app --host 0.0.0.0 --port "$GATEWAY_PORT" &
GATEWAY_PID=$!

cleanup() {
    kill "$GATEWAY_PID" "$WATCHER_PID" "$TRINO_PID" 2>/dev/null || true
}
trap cleanup INT TERM EXIT
wait "$TRINO_PID"
