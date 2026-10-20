#!/bin/bash
set -e

# Creates the Container Apps environment (run build-images.sh first, deploy-azure.sh after).
# Kept separate from deploy-azure.sh because it is slow, so CI can refresh its Azure login in between.

RESOURCE_GROUP="${RESOURCE_GROUP:-kicklab-rg}"

echo "=== KICKLAB Container Apps Environment ==="

ENV_NAME=$(az group show --name "$RESOURCE_GROUP" --query "tags.envName" -o tsv)
LOCATION=$(az group show --name "$RESOURCE_GROUP" --query "tags.location" -o tsv)

if [[ -z "$ENV_NAME" || -z "$LOCATION" ]]; then
  echo "Resource group $RESOURCE_GROUP is missing deployment tags. Run scripts/deploy/env-setup.sh first." >&2
  exit 1
fi

if az containerapp env show --name "$ENV_NAME" --resource-group "$RESOURCE_GROUP" >/dev/null 2>&1; then
  echo "Container Apps environment $ENV_NAME already exists, reusing it."
else
  echo "Creating Container Apps environment $ENV_NAME (this can take several minutes)..."
  az containerapp env create --name "$ENV_NAME" --resource-group "$RESOURCE_GROUP" --location "$LOCATION" -o none
fi

# Every app's address is <app>.<domain> (public) or <app>.internal.<domain> (internal),
# so saving the domain lets deploy-azure.sh work out all addresses before deploying anything
ENV_DOMAIN=$(az containerapp env show --name "$ENV_NAME" --resource-group "$RESOURCE_GROUP" \
  --query properties.defaultDomain -o tsv)
az group update --name "$RESOURCE_GROUP" --set tags.envDomain="$ENV_DOMAIN" -o none

echo "Environment domain: $ENV_DOMAIN"
echo "=== Container Apps Environment Ready ==="