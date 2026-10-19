#!/bin/bash
set -e

# Deploys (creates or updates) every app in apps.conf to the existing Container Apps environment.
# Run identity-setup.sh, env-setup.sh, build-images.sh and deploy-azure-env.sh first.

RESOURCE_GROUP="${RESOURCE_GROUP:-kicklab-rg}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APPS_FILE="$SCRIPT_DIR/apps.conf"
PULL_IDENTITY_NAME="kicklab-acr-pull"

echo "=== KICKLAB Azure Deployment ==="

tag() { az group show --name "$RESOURCE_GROUP" --query "tags.$1" -o tsv; }
REGISTRY_NAME=$(tag registryName)
ENV_NAME=$(tag envName)
ENV_DOMAIN=$(tag envDomain)
IMAGE_TAG=$(tag imageTag)
LOCATION=$(tag location)

if [[ -z "$REGISTRY_NAME" || -z "$ENV_NAME" || -z "$ENV_DOMAIN" || -z "$IMAGE_TAG" ]]; then
  echo "Missing deployment tags. Run env-setup.sh, build-images.sh and deploy-azure-env.sh first." >&2
  exit 1
fi

: "${STAFF_PASSWORD:?Set STAFF_PASSWORD (the cloud staff login password) before deploying}"
export SECRET_KEY="${SECRET_KEY:-$(openssl rand -hex 32)}"
export ORDERS_MCP_SECRET="${ORDERS_MCP_SECRET:-$(openssl rand -hex 32)}"

LOGIN_SERVER=$(az acr show --name "$REGISTRY_NAME" --resource-group "$RESOURCE_GROUP" --query loginServer -o tsv)
REGISTRY_ID=$(az acr show --name "$REGISTRY_NAME" --resource-group "$RESOURCE_GROUP" --query id -o tsv)
ENV_ID=$(az containerapp env show --name "$ENV_NAME" --resource-group "$RESOURCE_GROUP" --query id -o tsv)

# One shared identity that all apps use to pull images (one AcrPull assignment instead of fourteen)
if ! az identity show --resource-group "$RESOURCE_GROUP" --name "$PULL_IDENTITY_NAME" >/dev/null 2>&1; then
  az identity create --resource-group "$RESOURCE_GROUP" --name "$PULL_IDENTITY_NAME" -o none
  echo "Created image-pull identity $PULL_IDENTITY_NAME."
fi
PULL_ID=$(az identity show --resource-group "$RESOURCE_GROUP" --name "$PULL_IDENTITY_NAME" --query id -o tsv)
PULL_PRINCIPAL_ID=$(az identity show --resource-group "$RESOURCE_GROUP" --name "$PULL_IDENTITY_NAME" --query principalId -o tsv)

for ATTEMPT in 1 2 3 4 5 6; do
  OUTPUT=$(az role assignment create --assignee-object-id "$PULL_PRINCIPAL_ID" \
    --assignee-principal-type ServicePrincipal --role AcrPull --scope "$REGISTRY_ID" -o none 2>&1) && {
    echo "Granted AcrPull to $PULL_IDENTITY_NAME."; break; }
  if echo "$OUTPUT" | grep -qi "already exists"; then echo "AcrPull already granted."; break; fi
  echo "Waiting for the pull identity to propagate (attempt $ATTEMPT)..."
  sleep 15
  if [[ "$ATTEMPT" -eq 6 ]]; then echo "$OUTPUT" >&2; exit 1; fi
done

export ENV_DOMAIN LOGIN_SERVER IMAGE_TAG ENV_ID PULL_ID LOCATION STAFF_PASSWORD

# Specs contain secret values, so they live in a temporary folder that is deleted on exit
SPEC_DIR=$(mktemp -d)
trap 'rm -rf "$SPEC_DIR"' EXIT

APP_NAMES=$(grep -v '^#' "$APPS_FILE" | grep -v '^[[:space:]]*$' | cut -d'|' -f1)

for NAME in $APP_NAMES; do
  python3 "$SCRIPT_DIR/render_app_spec.py" "$APPS_FILE" "$NAME" > "$SPEC_DIR/$NAME.yaml"
  if az containerapp show --name "$NAME" --resource-group "$RESOURCE_GROUP" >/dev/null 2>&1; then
    echo "Updating $NAME..."
    az containerapp update --name "$NAME" --resource-group "$RESOURCE_GROUP" --yaml "$SPEC_DIR/$NAME.yaml" -o none
  else
    echo "Creating $NAME..."
    az containerapp create --name "$NAME" --resource-group "$RESOURCE_GROUP" --yaml "$SPEC_DIR/$NAME.yaml" -o none
  fi
done

echo "=== Deployment Complete ==="
echo "Public apps:"
grep -v '^#' "$APPS_FILE" | grep -v '^[[:space:]]*$' | while IFS='|' read -r NAME _ _ INGRESS _; do
  [[ "$INGRESS" == "external" ]] && echo "  $NAME: https://$NAME.$ENV_DOMAIN"
done