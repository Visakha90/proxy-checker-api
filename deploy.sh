#!/bin/bash
# ProxyChecker Deployment Script for Ubuntu 24 LTS
# Run as root on your VPS: bash deploy.sh

set -e

echo "=========================================="
echo "  ProxyChecker Deployment"
echo "  Domain: kaliptosal.dev"
echo "=========================================="

# 1. Update system
echo "[1/8] Updating system..."
apt-get update -y && apt-get upgrade -y

# 2. Install Docker
echo "[2/8] Installing Docker..."
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com | sh
    systemctl enable docker
    systemctl start docker
fi
docker --version

# 3. Install Docker Compose
echo "[3/8] Installing Docker Compose..."
if ! command -v docker-compose &> /dev/null; then
    apt-get install -y docker-compose-plugin
fi

# 4. Install Git
echo "[4/8] Installing Git..."
apt-get install -y git

# 5. Clone repo
echo "[5/8] Cloning repository..."
cd /opt
if [ -d "proxy-checker-api" ]; then
    cd proxy-checker-api
    git pull origin main
else
    git clone https://github.com/Visakha90/proxy-checker-api.git
    cd proxy-checker-api
fi

# 6. Create .env file
echo "[6/8] Creating .env..."

# Generate a URL-SAFE database password (alphanumeric only).
# This avoids percent-encoding pitfalls in DATABASE_URL entirely.
if [ -f .env ] && grep -q '^POSTGRES_PASSWORD=' .env; then
    DB_PASS=$(grep '^POSTGRES_PASSWORD=' .env | cut -d= -f2-)
    echo "  Reusing existing database password"
else
    DB_PASS=$(openssl rand -hex 24)
    echo "  Generated new URL-safe database password"
fi
SECRET_KEY=$(openssl rand -hex 32)

cat > .env << EOF
# Database
# NOTE: POSTGRES_PASSWORD is intentionally alphanumeric (hex) so that it is
# URL-safe and requires no percent-encoding inside DATABASE_URL.
POSTGRES_USER=proxydb
POSTGRES_PASSWORD=${DB_PASS}
POSTGRES_DB=proxy_checker
DATABASE_URL=postgresql+asyncpg://proxydb:${DB_PASS}@db:5432/proxy_checker

# Redis
REDIS_URL=redis://redis:6379/0

# Backend
SECRET_KEY=${SECRET_KEY}
ADMIN_USERNAME=admin
ADMIN_PASSWORD=@zy_sal90
ACCESS_TOKEN_EXPIRE_MINUTES=1440

# Scraper Settings
SCRAPE_INTERVAL_SECONDS=10
CHECK_INTERVAL_SECONDS=30
CHECK_CONCURRENCY=500
CHECK_TIMEOUT=10
MAX_FAILURES_BEFORE_DELETE=3
MAX_PROXY_AGE_HOURS=24
RETRY_COUNT=2

# Name.com DNS
NAMECOM_USERNAME=yeychanthy168169@gmail.com
NAMECOM_API_TOKEN=b4ab6ca90ca353459062840a6a9a8e77d3dbcdd0

# Telegram Admin
TELEGRAM_BOT_TOKEN=
TELEGRAM_ADMIN_CHAT_ID=

# Stripe
STRIPE_SECRET_KEY=
STRIPE_WEBHOOK_SECRET=

# Frontend
NEXT_PUBLIC_API_URL=https://api.kaliptosal.dev
NEXT_PUBLIC_WS_URL=wss://api.kaliptosal.dev
EOF

echo "[7/8] Building and starting services..."
docker compose up --build -d

# 7. Wait for services to be healthy
echo "Waiting for services to start..."
sleep 15

# 8. Install Nginx + SSL with Certbot
echo "[8/8] Setting up Nginx + SSL..."
apt-get install -y nginx certbot python3-certbot-nginx

# Configure Nginx
cat > /etc/nginx/sites-available/proxychecker << 'NGINX'
server {
    listen 80;
    server_name kaliptosal.dev www.kaliptosal.dev api.kaliptosal.dev;

    # Gzip
    gzip on;
    gzip_types text/plain text/csv application/json text/css application/javascript;
    gzip_min_length 256;

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;

    # API backend
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # WebSocket
    location /ws {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 86400;
    }

    # Swagger docs
    location /docs {
        proxy_pass http://127.0.0.1:8000;
    }

    location /openapi.json {
        proxy_pass http://127.0.0.1:8000;
    }

    # Health/metrics
    location /health {
        proxy_pass http://127.0.0.1:8000;
    }

    location /metrics {
        proxy_pass http://127.0.0.1:8000;
    }

    location /ready {
        proxy_pass http://127.0.0.1:8000;
    }

    # Frontend
    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    # Next.js HMR
    location /_next/ {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
NGINX

# Enable site
ln -sf /etc/nginx/sites-available/proxychecker /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

# Get SSL certificate
echo "Getting SSL certificate..."
certbot --nginx -d kaliptosal.dev -d www.kaliptosal.dev -d api.kaliptosal.dev --non-interactive --agree-tos --email yeychanthy168169@gmail.com || echo "SSL setup may need manual attention"

# Auto-renew
echo "0 0 * * * root certbot renew --quiet" > /etc/cron.d/certbot-renew

echo ""
echo "=========================================="
echo "  DEPLOYMENT COMPLETE!"
echo "=========================================="
echo ""
echo "  Frontend: https://kaliptosal.dev"
echo "  API:      https://api.kaliptosal.dev"
echo "  Swagger:  https://api.kaliptosal.dev/docs"
echo "  Admin:    admin / @zy_sal90"
echo ""
echo "  Docker:   docker compose logs -f"
echo "  Status:   docker compose ps"
echo "=========================================="
