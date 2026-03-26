#!/usr/bin/env bash
# Server deployment script for 1177.pdhc
# Usage: ./server_deploy.sh <tarball> [install|update]
set -e

TARBALL="$1"
MODE="${2:-install}"
DEPLOY_DIR="/usr/local/www/1177.pdhc"
APP_PORT=9036
DB_PORT=9037

if [ -z "$TARBALL" ]; then
    echo "Usage: $0 <tarball> [install|update]"
    exit 1
fi

if [ ! -f "$TARBALL" ]; then
    echo "ERROR: Tarball not found: $TARBALL"
    exit 1
fi

echo "=== 1177.pdhc server deployment ==="
echo "Mode: ${MODE}"
echo "Deploy to: ${DEPLOY_DIR}"

sudo mkdir -p "$DEPLOY_DIR"
sudo chown "$(whoami):staff" "$DEPLOY_DIR"

if [ "$MODE" = "update" ]; then
    echo "Backing up current installation..."
    BACKUP_DIR="${DEPLOY_DIR}/backups/$(date -u +%Y-%m-%dT%H-%M-%SZ)"
    mkdir -p "$BACKUP_DIR"
    cp "${DEPLOY_DIR}/.env" "$BACKUP_DIR/.env" 2>/dev/null || true
    echo "Backup saved to: $BACKUP_DIR"

    echo "Stopping current application..."
    lsof -ti :$APP_PORT 2>/dev/null | xargs kill -TERM 2>/dev/null || true
    sleep 2
fi

echo "Extracting deployment package..."
tar xzf "$TARBALL" -C "$DEPLOY_DIR"

cd "$DEPLOY_DIR"

if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi
source venv/bin/activate
pip install -q -r requirements.txt

if [ ! -f ".env" ]; then
    cp .env.example .env
    chmod 600 .env
    echo "WARNING: Using .env.example — edit with production values!"
fi

if [ "$MODE" = "install" ]; then
    echo "Starting PostgreSQL on port ${DB_PORT}..."
    docker-compose up -d db
    echo "Waiting for database..."
    for i in $(seq 1 30); do
        if docker-compose exec -T db pg_isready -U forms_user -d forms_1177 >/dev/null 2>&1; then
            echo "Database ready."
            break
        fi
        if [ "$i" -eq 30 ]; then
            echo "ERROR: Database did not become ready."
            exit 1
        fi
        sleep 1
    done

    echo "Initializing database tables..."
    python app/scripts/init_db.py

    echo "Creating bootstrap admin user..."
    python app/scripts/create_admin.py
fi

chmod +x safe_restart.sh

mkdir -p "$DEPLOY_DIR/db_backups"

echo ""
echo "=== Deployment complete ==="
echo ""
if [ "$MODE" = "install" ]; then
    echo "First install steps:"
    echo "  1. Edit .env:     nano ${DEPLOY_DIR}/.env"
    echo "  2. Start app:     cd ${DEPLOY_DIR} && ./safe_restart.sh"
    echo "  3. Health check:  curl http://127.0.0.1:${APP_PORT}/api/health"
    echo ""
    echo "nginx setup:"
    echo "  4. sudo cp server_configs/nginx_1177.pdhc.se /opt/homebrew/etc/nginx/sites-available/1177.pdhc.se.conf"
    echo "  5. sudo ln -s /opt/homebrew/etc/nginx/sites-available/1177.pdhc.se.conf /opt/homebrew/etc/nginx/sites-enabled/"
    echo "  6. sudo nginx -t && sudo nginx -s reload"
else
    echo "Update steps:"
    echo "  1. Start app:    cd ${DEPLOY_DIR} && ./safe_restart.sh"
    echo "  2. Health check:  curl http://127.0.0.1:${APP_PORT}/api/health"
fi
