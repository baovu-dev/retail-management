#!/bin/bash
set -e

# Tags the deployment resource group with generated deployment names (single source of truth).
# The resource group itself is created once by identity-setup.sh.

RESOURCE_GROUP="${RESOURCE_GROUP:-kicklab-rg}"

echo "=== KICKLAB Environment Setup ==="

if ! az group show --name "$RESOURCE_GROUP" >/dev/null 2>&1; then
  echo "Resource group $RESOURCE_GROUP not found. Run scripts/deploy/identity-setup.sh first." >&2
  exit 1
fi

EXISTING_REGISTRY=$(az group show --name "$RESOURCE_GROUP" --query "tags.registryName" -o tsv 2>/dev/null || true)

if [[ -n "$EXISTING_REGISTRY" ]]; then
  echo "Resource group $RESOURCE_GROUP is already configured, reusing existing names."
  az group show --name "$RESOURCE_GROUP" --query tags -o table
  exit 0
fi

LOCATION=$(az group show --name "$RESOURCE_GROUP" --query location -o tsv)
REGISTRY_NAME="kicklabacr${RANDOM}${RANDOM}"   # must be globally unique, letters and numbers only
ENV_NAME="kicklab-env"

echo "Tagging resource group with deployment names..."
az group update --name "$RESOURCE_GROUP" \
  --tags registryName="$REGISTRY_NAME" envName="$ENV_NAME" location="$LOCATION" -o none

echo "=== Environment Setup Complete ==="
az group show --name "$RESOURCE_GROUP" --query tags -o table