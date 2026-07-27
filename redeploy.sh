#!/bin/bash
#
# ProxyChecker Redeploy Script
# Compatible with Docker Compose v1 (docker-compose) AND v2 (docker compose).
#
# Usage on the VPS:
#   cd /opt/proxy-checker-api && bash redeploy.sh
#
# Or one-liner:
#   curl -fsSL https://raw.githubusercontent.com/Visakha90/proxy-checker-api/main/redeploy.sh | bash

set -uo pipefail

PROJECT_DIR="${PROJECT_DIR:-/opt/proxy-checker-api}"
REPO_URL="https://github.com/Visakha90/proxy-checker-api.git"

# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
ok()   { echo -e "${GREEN}[OK]${NC}   $*"; }
fail() { echo -e "${RED}[FAIL]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
info() { echo -e "${BLUE}[..]${NC}   $*"; }

# ─────────────────────────────────────────────────────────────
# 1. Detect Docker Compose command (v2 plugin vs v1 standalone)
# ─────────────────────────────────────────────────────────────
detect_compose() {
    # Prefer v2 plugin
    if docker compose version >/dev/null 2>&1; then
        DC="docker compose"
        DC_VERSION=$(docker compose version --short 2>/dev/null || echo "v2")
        ok "Detected Docker Compose v2 (plugin): $DC_VERSION"
        return 0
    fi

    # Fall back to v1 standalone binary
    if command -v docker-compose >/dev/null 2>&1; then
        DC="docker-compose"
        DC_VERSION=$(docker-compose version --short 2>/dev/null || echo "v1")
        ok "Detected Docker Compose v1 (standalone): $DC_VERSION"
        return 0
    fi

    # Neither found -> install the v2 plugin
    warn "No Docker Compose found. Installing v2 plugin..."
    if command -v apt-get >/dev/null 2>&1; then
        apt-get update -y -qq
        apt-get install -y -qq docker-compose-plugin 2>/dev/null || true
    fi

    if docker compose version >/dev/null 2>&1; then
        DC="docker compose"
        ok "Installed Docker Compose v2 plugin"
        return 0
    fi

    # Last resort: download the standalone binary
    warn "Plugin install failed. Downloading standalone binary..."
    ARCH=$(uname -m)
    curl -fsSL "https://github.com/docker/compose/releases/latest/download/docker-compose-linux-${ARCH}" \
        -o /usr/local/bin/docker-compose
    chmod +x /usr/local/bin/docker-compose

    if command -v docker-compose >/dev/null 2>&1; then
        DC="docker-compose"
        ok "Installed Docker Compose standalone binary"
        return 0
    fi

    fail "Could not install Docker Compose. Aborting."
    exit 1
}

echo "=========================================="
echo "  ProxyChecker Redeploy"
echo "=========================================="
echo ""

info "Step 1/8: Detecting Docker Compose..."
detect_compose
echo "  Using command: $DC"
echo ""

# ─────────────────────────────────────────────────────────────
# 2. Ensure project directory and pull latest code
# ─────────────────────────────────────────────────────────────
info "Step 2/8: Pulling latest code..."
if [ ! -d "$PROJECT_DIR/.git" ]; then
    warn "Project not found at $PROJECT_DIR. Cloning..."
    mkdir -p "$(dirname "$PROJECT_DIR")"
    git clone "$REPO_URL" "$PROJECT_DIR"
fi

cd "$PROJECT_DIR" || { fail "Cannot cd to $PROJECT_DIR"; exit 1; }

git fetch origin main
git reset --hard origin/main
COMMIT=$(git rev-parse --short HEAD)
COMMIT_FULL=$(git rev-parse HEAD)
COMMIT_MSG=$(git log -1 --pretty=%s)
ok "At commit $COMMIT — $COMMIT_MSG"
echo ""

# ─────────────────────────────────────────────────────────────
# 3. Validate .env exists and DATABASE_URL is consistent
# ─────────────────────────────────────────────────────────────
info "Step 3/8: Validating .env..."
if [ ! -f .env ]; then
    fail ".env not found. Run deploy.sh first for initial setup."
    exit 1
fi

# Extract POSTGRES_PASSWORD and verify DATABASE_URL matches (percent-encoded)
PG_PASS=$(grep '^POSTGRES_PASSWORD=' .env | cut -d= -f2- || echo "")
DB_URL=$(grep '^DATABASE_URL=' .env | cut -d= -f2- || echo "")

if [ -z "$PG_PASS" ]; then
    fail "POSTGRES_PASSWORD missing from .env"
    exit 1
fi

# Percent-encode the password for URL use
url_encode() {
    python3 -c "import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1], safe=''))" "$1" 2>/dev/null \
        || echo "$1"
}
PG_PASS_ENC=$(url_encode "$PG_PASS")
EXPECTED_URL="postgresql+asyncpg://proxydb:${PG_PASS_ENC}@db:5432/proxy_checker"

if [ "$DB_URL" != "$EXPECTED_URL" ]; then
    warn "DATABASE_URL does not match POSTGRES_PASSWORD (encoding mismatch)."
    warn "  Current:  $DB_URL"
    warn "  Expected: $EXPECTED_URL"
    info "Correcting DATABASE_URL in .env..."
    # Use a delimiter unlikely to appear in the URL
    sed -i "s|^DATABASE_URL=.*|DATABASE_URL=${EXPECTED_URL}|" .env
    ok "DATABASE_URL corrected"
else
    ok "DATABASE_URL matches POSTGRES_PASSWORD"
fi
echo ""

# ─────────────────────────────────────────────────────────────
# 4. Stop containers
# ─────────────────────────────────────────────────────────────
info "Step 4/8: Stopping containers..."
$DC down --remove-orphans 2>&1 | tail -5 || warn "down returned non-zero (may be first run)"
ok "Containers stopped"
echo ""

# ─────────────────────────────────────────────────────────────
# 5. Rebuild backend WITHOUT cache
# ─────────────────────────────────────────────────────────────
info "Step 5/8: Rebuilding images (no cache)..."
if ! $DC build --no-cache backend; then
    fail "Backend build failed"
    exit 1
fi
ok "Backend image rebuilt from scratch"

# Rebuild frontend too (cached is fine, deps rarely change)
$DC build frontend 2>&1 | tail -5 || warn "Frontend build had warnings"
ok "Frontend image built"
echo ""

# ─────────────────────────────────────────────────────────────
# 6. Start containers
# ─────────────────────────────────────────────────────────────
info "Step 6/8: Starting containers..."
if ! $DC up -d; then
    fail "Failed to start containers"
    $DC logs --tail=50
    exit 1
fi
ok "Containers started"
echo ""

# ─────────────────────────────────────────────────────────────
# 7. Wait for backend and verify migrations
# ─────────────────────────────────────────────────────────────
info "Step 7/8: Waiting for backend to become healthy..."

BACKEND_UP=0
for i in $(seq 1 60); do
    if curl -fsS --max-time 3 http://127.0.0.1:8000/health >/dev/null 2>&1; then
        BACKEND_UP=1
        ok "Backend responded after ${i}0s"
        break
    fi
    # Detect crash loop early
    STATUS=$($DC ps backend 2>/dev/null | grep -i backend || echo "")
    if echo "$STATUS" | grep -qi "restarting"; then
        warn "Backend is restarting (attempt $i/60)..."
    fi
    sleep 3
done

if [ "$BACKEND_UP" -eq 0 ]; then
    fail "Backend did not become healthy within 180s"
    echo ""
    echo "─── BACKEND LOGS (last 60 lines) ───"
    $DC logs --tail=60 backend
    echo "─── CONTAINER STATUS ───"
    $DC ps
    exit 1
fi
echo ""

# Verify migrations actually ran
info "Verifying Alembic migrations..."
MIGRATION_OUT=$($DC exec -T backend alembic current 2>&1 || echo "FAILED")
if echo "$MIGRATION_OUT" | grep -q "head"; then
    ok "Migrations at head: $(echo "$MIGRATION_OUT" | grep -o '[0-9]* (head)')"
elif echo "$MIGRATION_OUT" | grep -qi "InvalidPassword"; then
    fail "DATABASE AUTH STILL FAILING:"
    echo "$MIGRATION_OUT"
    exit 1
else
    warn "Could not confirm migration state:"
    echo "$MIGRATION_OUT" | tail -5
fi
echo ""

# ─────────────────────────────────────────────────────────────
# 8. Verify endpoints + deployed commit
# ─────────────────────────────────────────────────────────────
info "Step 8/8: Verifying endpoints..."

check_endpoint() {
    local name="$1" url="$2"
    local code
    code=$(curl -o /dev/null -sS -w "%{http_code}" --max-time 10 "$url" 2>/dev/null || echo "000")
    if [ "$code" = "200" ]; then
        ok "$name -> $code"
        return 0
    else
        fail "$name -> $code"
        return 1
    fi
}

FAILED=0
check_endpoint "GET /health          " "http://127.0.0.1:8000/health" || FAILED=1
check_endpoint "GET /ready           " "http://127.0.0.1:8000/ready" || FAILED=1
check_endpoint "GET /docs            " "http://127.0.0.1:8000/docs" || FAILED=1
check_endpoint "GET /api/v1/stats    " "http://127.0.0.1:8000/api/v1/stats" || FAILED=1
check_endpoint "GET /api/stats       " "http://127.0.0.1:8000/api/stats" || FAILED=1
check_endpoint "GET /metrics         " "http://127.0.0.1:8000/metrics" || FAILED=1
echo ""

# Verify the running container has the expected commit
info "Verifying deployed commit inside container..."
CONTAINER_COMMIT=$($DC exec -T backend sh -c "cat /app/.deployed_commit 2>/dev/null || echo unknown" 2>/dev/null | tr -d '\r\n')
echo "$COMMIT_FULL" > "$PROJECT_DIR/backend/.deployed_commit"
ok "Host commit:      $COMMIT"
if [ "$CONTAINER_COMMIT" != "unknown" ] && [ -n "$CONTAINER_COMMIT" ]; then
    ok "Container commit: ${CONTAINER_COMMIT:0:7}"
fi

# Show image build time to prove it was rebuilt
IMAGE_CREATED=$(docker image inspect "$(basename "$PROJECT_DIR" | tr '[:upper:]' '[:lower:]' | tr -d '_-')_backend" --format '{{.Created}}' 2>/dev/null \
    || docker image inspect proxy-checker-api-backend --format '{{.Created}}' 2>/dev/null \
    || docker image inspect proxy-checker-api_backend --format '{{.Created}}' 2>/dev/null \
    || echo "unknown")
if [ "$IMAGE_CREATED" != "unknown" ]; then
    ok "Backend image built: $IMAGE_CREATED"
fi
echo ""

# ─────────────────────────────────────────────────────────────
# Final report
# ─────────────────────────────────────────────────────────────
echo "=========================================="
echo "  CONTAINER STATUS"
echo "=========================================="
$DC ps
echo ""

# Nginx + SSL checks
info "Checking Nginx and SSL..."
if systemctl is-active --quiet nginx 2>/dev/null; then
    ok "Nginx (host) is active"
elif $DC ps 2>/dev/null | grep -qi "nginx.*up"; then
    ok "Nginx (container) is up"
else
    warn "Nginx status unknown"
fi

for host in kaliptosal.dev api.kaliptosal.dev; do
    code=$(curl -o /dev/null -sS -w "%{http_code}" --max-time 10 "https://$host/health" 2>/dev/null || echo "000")
    if [ "$code" = "200" ]; then
        ok "https://$host/health -> 200 (SSL working)"
    else
        warn "https://$host/health -> $code"
    fi
done
echo ""

echo "=========================================="
if [ "$FAILED" -eq 0 ]; then
    echo -e "  ${GREEN}DEPLOYMENT SUCCESSFUL${NC}"
    echo "=========================================="
    echo "  Compose:  $DC"
    echo "  Commit:   $COMMIT"
    echo "  Message:  $COMMIT_MSG"
    echo ""
    echo "  Frontend: https://kaliptosal.dev"
    echo "  API:      https://kaliptosal.dev/api/v1/stats"
    echo "  Docs:     https://kaliptosal.dev/docs"
    echo "  Health:   https://kaliptosal.dev/health"
    echo "=========================================="
    exit 0
else
    echo -e "  ${RED}DEPLOYMENT COMPLETED WITH ERRORS${NC}"
    echo "=========================================="
    echo ""
    echo "─── BACKEND LOGS (last 40 lines) ───"
    $DC logs --tail=40 backend
    exit 1
fi
