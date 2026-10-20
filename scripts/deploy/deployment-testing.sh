#!/bin/bash
set -e

# Validates the cloud deployment and writes a deployment report as evidence.
# Retries each check because scale-to-zero apps can take a while to wake up.

RESOURCE_GROUP="${RESOURCE_GROUP:-kicklab-rg}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APPS_FILE="$SCRIPT_DIR/apps.conf"
REPORT_DIR="${REPORT_DIR:-docs/release-2/evidence/cloud}"
REPORT_FILE="$REPORT_DIR/deployment-results.md"

echo "=== KICKLAB Deployment Testing ==="

ENV_DOMAIN=$(az group show --name "$RESOURCE_GROUP" --query "tags.envDomain" -o tsv)
IMAGE_TAG=$(az group show --name "$RESOURCE_GROUP" --query "tags.imageTag" -o tsv)
if [[ -z "$ENV_DOMAIN" ]]; then
  echo "Missing envDomain tag. Run deploy-azure-env.sh and deploy-azure.sh first." >&2
  exit 1
fi
REVIEWS="https://student1-backend.$ENV_DOMAIN"

# HTTP status of a request, retrying while apps wake up. Extra curl options can be passed after the URL.
http_status() {
  local url="$1"; shift
  local code=""
  for attempt in 1 2 3 4; do
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 60 "$@" "$url" || true)
    [[ "$code" =~ ^[23] || "$code" == "403" || "$code" == "404" ]] && break    
    sleep 10
  done
  echo "${code:-000}"
}

FAILED=0
mkdir -p "$REPORT_DIR"
{
  echo "# KICKLAB Cloud Deployment Report"
  echo ""
  echo "- Platform: Azure Container Apps"
  echo "- Environment domain: $ENV_DOMAIN"
  echo "- Image tag (commit): $IMAGE_TAG"
  echo "- Timestamp: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo ""
  echo "## 1. Public apps respond"
  echo ""
  echo "| App | URL | HTTP | Result |"
  echo "|---|---|---|---|"
} > "$REPORT_FILE"

grep -v '^#' "$APPS_FILE" | grep -v '^[[:space:]]*$' | while IFS='|' read -r NAME _ _ INGRESS _; do
  [[ "$INGRESS" == "external" ]] || continue
  URL="https://$NAME.$ENV_DOMAIN"
  CODE=$(http_status "$URL")
  # 404 at the root still proves the app is up (API-only backends have no page at "/")
  RESULT=$([[ "$CODE" =~ ^[23] || "$CODE" == "404" ]] && echo PASS || echo FAIL)
  echo "  $NAME -> $CODE ($RESULT)"
  echo "| $NAME | $URL | $CODE | $RESULT |" >> "$REPORT_FILE"
done
grep -q "| FAIL |" "$REPORT_FILE" && FAILED=1

# Frontend -> backend -> database: Reviews stats come from the internal database
STATS=$(curl -s --max-time 60 "$REVIEWS/reviews/stats" || true)
if echo "$STATS" | grep -q "total_reviews"; then CHAIN="PASS"; else CHAIN="FAIL"; FAILED=1; fi
echo "  Reviews backend -> database: $CHAIN ($STATS)"

# Cloud baseline: AI services must be disabled by default
AI_PAGE=$(curl -s --max-time 60 "$REVIEWS/reviews/view?product_id=101" || true)
if echo "$AI_PAGE" | grep -q "AI features are disabled"; then AI="PASS"; else AI="FAIL"; FAILED=1; fi
MCP=$(http_status "$REVIEWS/mcp/rating-summary" -X POST -d "product_id=101")
RAG=$(http_status "$REVIEWS/rag/answer" -X POST -d "query=test")
MA=$(http_status "$REVIEWS/multi-agent/workflow" -X POST -H "Content-Type: application/json" -d '{"user_request":"test"}')
for CODE in "$MCP" "$RAG" "$MA"; do [[ "$CODE" == "403" ]] || FAILED=1; done
echo "  AI-Mode disabled: $AI | MCP: $MCP | RAG: $RAG | Multi-Agent: $MA (403 = disabled)"

{
  echo ""
  echo "## 2. Integration and cloud baseline"
  echo ""
  echo "| Check | Expected | Actual | Result |"
  echo "|---|---|---|---|"
  echo "| Reviews backend -> internal database (/reviews/stats) | JSON with total_reviews | \`$STATS\` | $CHAIN |"
  echo "| AI-Mode disabled (review summary) | \"AI features are disabled\" | see Result | $AI |"
  echo "| MCP disabled (/mcp/rating-summary) | 403 | $MCP | $([[ "$MCP" == "403" ]] && echo PASS || echo FAIL) |"
  echo "| RAG disabled (/rag/answer) | 403 | $RAG | $([[ "$RAG" == "403" ]] && echo PASS || echo FAIL) |"
  echo "| Multi-Agent disabled (/multi-agent/workflow) | 403 | $MA | $([[ "$MA" == "403" ]] && echo PASS || echo FAIL) |"
  echo ""
  echo "## 3. Internal-only apps (not reachable from the internet)"
  echo ""
  echo "| App | External ingress | Result |"
  echo "|---|---|---|"
} >> "$REPORT_FILE"

grep -v '^#' "$APPS_FILE" | grep -v '^[[:space:]]*$' | while IFS='|' read -r NAME _ _ INGRESS _; do
  [[ "$INGRESS" == "internal" ]] || continue
  EXTERNAL=$(az containerapp show --name "$NAME" --resource-group "$RESOURCE_GROUP" \
    --query properties.configuration.ingress.external -o tsv)
  RESULT=$([[ "$EXTERNAL" == "false" ]] && echo PASS || echo FAIL)
  echo "| $NAME | $EXTERNAL | $RESULT |" >> "$REPORT_FILE"
done
grep -q "| FAIL |" "$REPORT_FILE" && FAILED=1

{
  echo ""
  echo "## Overall: $([[ "$FAILED" -eq 0 ]] && echo PASS || echo FAIL)"
  echo ""
  echo "Human release decision: (pending Cloud Deployment Review)"
} >> "$REPORT_FILE"

echo "=== Report written to $REPORT_FILE ==="
cat "$REPORT_FILE"
exit "$FAILED"