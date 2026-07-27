#!/bin/bash
# ProxyChecker Health Check — run periodically or from monitoring
DOMAIN="${1:-kaliptosal.dev}"
FAILED=0

check() {
    local code
    code=$(curl -o /dev/null -sSk -w "%{http_code}" --max-time 10 "$1" 2>/dev/null || echo "000")
    if [ "$code" = "200" ]; then
        echo "✓ $2"
    else
        echo "✗ $2 (HTTP $code)"
        FAILED=$((FAILED + 1))
    fi
}

echo "Health Check: $DOMAIN"
echo "─────────────────────────────"
check "https://$DOMAIN/health" "Backend health"
check "https://$DOMAIN/ready" "Backend ready"
check "https://$DOMAIN/" "Frontend"
check "https://$DOMAIN/api/v1/stats" "API v1 stats"
check "https://$DOMAIN/docs" "Swagger docs"
check "https://$DOMAIN/metrics" "Prometheus metrics"
check "https://$DOMAIN/favicon.svg" "Favicon"

echo "─────────────────────────────"
if [ "$FAILED" -eq 0 ]; then
    echo "ALL CHECKS PASSED"
    exit 0
else
    echo "$FAILED CHECK(S) FAILED"
    exit 1
fi
