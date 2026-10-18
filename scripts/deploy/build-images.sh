#!/bin/bash
set -e

# Creates the Azure Container Registry (if needed) and builds/pushes one image per build folder.
# BUILD_MODE=acr (default) builds in Azure. BUILD_MODE=docker builds locally for linux/amd64 and pushes.

RESOURCE_GROUP="${RESOURCE_GROUP:-kicklab-rg}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APPS_FILE="$SCRIPT_DIR/apps.conf"
IMAGE_TAG="${IMAGE_TAG:-$(git rev-parse --short HEAD)}"
BUILD_MODE="${BUILD_MODE:-acr}"

echo "=== KICKLAB Image Build (tag: $IMAGE_TAG, mode: $BUILD_MODE) ==="

REGISTRY_NAME=$(az group show --name "$RESOURCE_GROUP" --query "tags.registryName" -o tsv)
if [[ -z "$REGISTRY_NAME" ]]; then
  echo "Resource group $RESOURCE_GROUP is missing deployment tags. Run scripts/deploy/env-setup.sh first." >&2
  exit 1
fi

if ! az acr show --name "$REGISTRY_NAME" --resource-group "$RESOURCE_GROUP" >/dev/null 2>&1; then
  echo "Creating Azure Container Registry $REGISTRY_NAME..."
  az acr create --resource-group "$RESOURCE_GROUP" --name "$REGISTRY_NAME" --sku Basic -o none
fi
LOGIN_SERVER=$(az acr show --name "$REGISTRY_NAME" --resource-group "$RESOURCE_GROUP" --query loginServer -o tsv)

# A new registry can report "created" before its address resolves (same issue the lab handles)
echo "Waiting for $LOGIN_SERVER to resolve..."
for i in $(seq 1 24); do
  if nslookup "$LOGIN_SERVER" >/dev/null 2>&1; then echo "$LOGIN_SERVER is resolvable."; break; fi
  if [[ "$i" -eq 24 ]]; then echo "Timed out waiting for $LOGIN_SERVER." >&2; exit 1; fi
  sleep 5
done

# One image per build folder listed in apps.conf
IMAGES=$(grep -v '^#' "$APPS_FILE" | grep -v '^[[:space:]]*$' | cut -d'|' -f2 | sort -u)

if [[ "$BUILD_MODE" == "docker" ]]; then
  az acr login --name "$REGISTRY_NAME"
fi

for IMAGE in $IMAGES; do
  echo "Building and pushing $IMAGE..."
  if [[ "$BUILD_MODE" == "docker" ]]; then
    docker build --platform linux/amd64 -t "$LOGIN_SERVER/$IMAGE:$IMAGE_TAG" -t "$LOGIN_SERVER/$IMAGE:latest" "./$IMAGE"
    docker push --all-tags "$LOGIN_SERVER/$IMAGE"
  else
    az acr build --registry "$REGISTRY_NAME" --image "$IMAGE:$IMAGE_TAG" --image "$IMAGE:latest" "./$IMAGE"
  fi
done

# Record which tag was built, so deploy-azure.sh deploys exactly these images
az group update --name "$RESOURCE_GROUP" --set tags.imageTag="$IMAGE_TAG" -o none

echo "=== Image Build Complete ==="