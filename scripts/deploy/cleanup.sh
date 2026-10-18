#!/bin/bash
set -e

# Deletes the deployment resource group (registry, environment and all apps) to stop billing.
# The GitHub login identity lives in a separate resource group and is kept.

RESOURCE_GROUP="${RESOURCE_GROUP:-kicklab-rg}"

echo "=== KICKLAB Cleanup ==="

if ! az group show --name "$RESOURCE_GROUP" >/dev/null 2>&1; then
  echo "Resource group $RESOURCE_GROUP not found, nothing to clean up."
  exit 0
fi

echo "This will permanently delete resource group: $RESOURCE_GROUP"
az group show --name "$RESOURCE_GROUP" --query tags -o table
echo ""
echo "Apps that will be deleted:"
az containerapp list --resource-group "$RESOURCE_GROUP" --query "[].name" -o tsv | sed 's/^/  /'

if [[ -z "${CI:-}" ]]; then
  read -r -p "Type the resource group name to confirm: " CONFIRM
  if [[ "$CONFIRM" != "$RESOURCE_GROUP" ]]; then
    echo "Confirmation did not match. Aborting." >&2
    exit 1
  fi
fi

az group delete --name "$RESOURCE_GROUP" --yes --no-wait

echo "=== Deletion started ==="
echo "Check progress with: az group show --name $RESOURCE_GROUP"
echo ""
echo "Note: the GitHub identity's permissions were scoped to $RESOURCE_GROUP, so they are removed too."
echo "Before deploying again, re-run: bash scripts/deploy/identity-setup.sh"