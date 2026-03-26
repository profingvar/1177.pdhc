#!/usr/bin/env bash
# Graceful restart of 1177.pdhc application.
set -e

export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
export DOCKER_HOST="${DOCKER_HOST:-unix://$HOME/.colima/default/docker.sock}"

APP_PORT=9036
DB_PORT=9037
DB_CONTAINER="forms_1177_db"
DB_USER="forms_user"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKUP_DIR="$SCRIPT_DIR/db_backups"
PID_FILE="$SCRIPT_DIR/gunicorn.pid"
HEALTH_URL="http://127.0.0.1:${APP_PORT}/api/health"

echo "=== 1177.pdhc safe restart — $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="

# --- 1. Database backup ---
echo "Backing up database..."
mkdir -p "$BACKUP_DIR"
BACKUP_FILE="$BACKUP_DIR/forms_1177_$(date -u +%Y-%m-%dT%H-%M-%SZ).sql.gz"

if docker ps --format '{{.Names}}' | grep -q "^${DB_CONTAINER}$"; then
    if docker exec "$DB_CONTAINER" pg_dumpall -U "$DB_USER" 2>/dev/null | gzip > "$BACKUP_FILE"; then
        BACKUP_SIZE=$(stat -f%z "$BACKUP_FILE" 2>/dev/null || stat -c%s "$BACKUP_FILE" 2>/dev/null || echo "0")
        if [ "$BACKUP_SIZE" -gt 100 ]; then
            echo "Backup OK: $BACKUP_FILE (${BACKUP_SIZE} bytes)"
        else
            echo "WARNING: Backup file suspiciously small — may be empty"
            rm -f "$BACKUP_FILE"
        fi
    else
        echo "WARNING: Database backup failed — continuing"
        rm -f "$BACKUP_FILE"
    fi
else
    echo "WARNING: Database container not running — skipping backup"
fi

# Rotate backups — keep last 10
BACKUP_COUNT=$(ls -1 "$BACKUP_DIR"/*.sql.gz 2>/dev/null | wc -l | tr -d ' ')
if [ "$BACKUP_COUNT" -gt 10 ]; then
    ls -1t "$BACKUP_DIR"/*.sql.gz | tail -n +11 | xargs rm -f
fi

# --- 2. Stop existing gunicorn ---
echo "Stopping application on port ${APP_PORT}..."
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    kill -TERM "$PID" 2>/dev/null || true
    sleep 2
    kill -9 "$PID" 2>/dev/null || true
    rm -f "$PID_FILE"
fi
lsof -ti :$APP_PORT 2>/dev/null | xargs kill -TERM 2>/dev/null || true
sleep 1
lsof -ti :$APP_PORT 2>/dev/null | xargs kill -9 2>/dev/null || true

# --- 3. Ensure database is running ---
echo "Checking database..."
cd "$SCRIPT_DIR"
if ! docker-compose exec -T db pg_isready -U "$DB_USER" -d forms_1177 >/dev/null 2>&1; then
    echo "Restarting database..."
    docker-compose up -d db
    for i in 1 2 3 4 5; do
        sleep 2
        if docker-compose exec -T db pg_isready -U "$DB_USER" -d forms_1177 >/dev/null 2>&1; then
            echo "Database ready after ${i} checks"
            break
        fi
        if [ "$i" -eq 5 ]; then
            echo "ERROR: Database not ready after 10s — aborting"
            exit 1
        fi
    done
fi

# --- 4. Activate venv and start gunicorn ---
source "$SCRIPT_DIR/venv/bin/activate"

echo "Starting application on port ${APP_PORT}..."
cd "$SCRIPT_DIR"
gunicorn \
    --bind 127.0.0.1:${APP_PORT} \
    --workers 2 \
    --timeout 30 \
    --daemon \
    --pid "$PID_FILE" \
    "app:create_app()"

# --- 5. Health check ---
echo "Verifying health..."
for i in 1 2 3; do
    sleep 2
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$HEALTH_URL" 2>/dev/null || echo "000")
    if [ "$HTTP_CODE" = "200" ]; then
        echo "Health check: OK (attempt $i)"
        exit 0
    fi
    echo "Health check attempt $i: HTTP ${HTTP_CODE}"
done

echo "ERROR: Health check failed"
exit 1
