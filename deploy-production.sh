#!/bin/bash
# ══════════════════════════════════════════════════════════════
# ProxyChecker — Production Deployment with HTTPS
# Run on VPS: bash deploy-production.sh
# ══════════════════════════════════════════════════════════════
set -euo pipefail

DOMAIN="kaliptosal.dev"
EMAIL="yeychanthy168169@gmail.com"
PROJECT_DIR="/opt/proxy-checker-api"

echo "═══════════════════════════════════════════"
echo "  Production Deployment: $DOMAIN"
echo "═══════════════════════════════════════════"

# ─── Detect Docker Compose ────────────────────────────────────────────────────
if docker compose version >/dev/null 2>&1; then DC="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then DC="docker-compose"
else echo "ERROR: Docker Compose not found"; exit 1; fi
echo "Using: $DC"

# ─── Pull latest code ─────────────────────────────────────────────────────────
cd "$PROJECT_DIR"
git fetch origin main
git reset --hard origin/main
echo "Code updated: $(git log -1 --oneline)"

# ─── Ensure .env exists ───────────────────────────────────────────────────────
if [ ! -f .env ]; then
    echo "ERROR: .env not found. Run the initial deploy.sh first."
    exit 1
fi

# ─── Step 1: Get SSL certificate (if not already done) ────────────────────────
if [ ! -f "certbot/conf/live/$DOMAIN/fullchain.pem" ]; then
    echo ""
    echo "[SSL] Obtaining Let's Encrypt certificate..."

    # Start a temporary nginx for the ACME challenge
    mkdir -p certbot/www certbot/conf

    # Write a minimal HTTP-only nginx config for certbot
    cat > nginx/nginx.conf.tmp << 'TMPCONF'
server {
    listen 80;
    server_name kaliptosal.dev www.kaliptosal.dev;
    location /.well-known/acme-challenge/ { root /var/www/certbot; }
    location / { return 200 'waiting for ssl'; }
}
TMPCONF

    # Start nginx with temp config
    docker run -d --name certbot-nginx --rm \
        -p 80:80 \
        -v "$PROJECT_DIR/nginx/nginx.conf.tmp:/etc/nginx/conf.d/default.conf:ro" \
        -v "$PROJECT_DIR/certbot/www:/var/www/certbot" \
        nginx:alpine

    sleep 3

    # Run certbot
    docker run --rm \
        -v "$PROJECT_DIR/certbot/www:/var/www/certbot" \
        -v "$PROJECT_DIR/certbot/conf:/etc/letsencrypt" \
        certbot/certbot certonly \
        --webroot \
        --webroot-path=/var/www/certbot \
        --email "$EMAIL" \
        --agree-tos \
        --no-eff-email \
        -d "$DOMAIN" \
        -d "www.$DOMAIN"

    # Stop temp nginx
    docker stop certbot-nginx 2>/dev/null || true
    rm -f nginx/nginx.conf.tmp

    echo "[SSL] Certificate obtained!"
else
    echo "[SSL] Certificate already exists. Checking renewal..."
    docker run --rm \
        -v "$PROJECT_DIR/certbot/conf:/etc/letsencrypt" \
        -v "$PROJECT_DIR/certbot/www:/var/www/certbot" \
        certbot/certbot renew --quiet || true
fi

# ─── Step 2: Stop old containers ──────────────────────────────────────────────
echo ""
echo "[DEPLOY] Stopping containers..."
$DC down --remove-orphans 2>/dev/null || true

# ─── Step 3: Build production images ─────────────────────────────────────────
echo ""
echo "[DEPLOY] Building production images..."
$DC build --no-cache backend frontend

# ─── Step 4: Start all services ───────────────────────────────────────────────
echo ""
echo "[DEPLOY] Starting services..."
$DC up -d

# ─── Step 5: Wait for health ──────────────────────────────────────────────────
echo ""
echo "[VERIFY] Waiting for services..."
sleep 15

for i in $(seq 1 30); do
    if curl -fsSk --max-time 5 https://$DOMAIN/health >/dev/null 2>&1; then
        echo "[VERIFY] HTTPS health check passed!"
        break
    fi
    if [ "$i" -eq 30 ]; then
        echo "[ERROR] Health check failed after 150s"
        $DC logs --tail=30 backend
        exit 1
    fi
    sleep 5
done

# ─── Step 6: Verify endpoints ─────────────────────────────────────────────────
echo ""
echo "[VERIFY] Checking endpoints..."
check() {
    local code
    code=$(curl -o /dev/null -sSk -w "%{http_code}" --max-time 10 "$1" 2>/dev/null || echo "000")
    if [ "$code" = "200" ] || [ "$code" = "301" ]; then
        echo "  ✓ $2 -> $code"
    else
        echo "  ✗ $2 -> $code"
    fi
}

check "https://$DOMAIN/" "Frontend"
check "https://$DOMAIN/health" "Health"
check "https://$DOMAIN/api/v1/stats" "API Stats"
check "https://$DOMAIN/docs" "Swagger"
check "https://$DOMAIN/metrics" "Metrics"
check "https://$DOMAIN/favicon.svg" "Favicon"
check "http://$DOMAIN/" "HTTP->HTTPS redirect"

# ─── Step 7: Set up auto-renewal cron ─────────────────────────────────────────
echo ""
echo "[SSL] Setting up auto-renewal..."
cat > /etc/cron.d/certbot-renew << EOF
0 3 * * * root cd $PROJECT_DIR && docker run --rm -v "$PROJECT_DIR/certbot/conf:/etc/letsencrypt" -v "$PROJECT_DIR/certbot/www:/var/www/certbot" certbot/certbot renew --quiet && $DC exec nginx nginx -s reload
EOF

echo ""
echo "═══════════════════════════════════════════"
echo "  DEPLOYMENT COMPLETE"
echo "═══════════════════════════════════════════"
echo ""
echo "  https://$DOMAIN"
echo "  https://$DOMAIN/dashboard"
echo "  https://$DOMAIN/docs"
echo ""
echo "  Commit: $(git rev-parse --short HEAD)"
echo "  Compose: $DC"
echo "═══════════════════════════════════════════"
