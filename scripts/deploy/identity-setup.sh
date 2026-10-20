#!/bin/bash
set -e

# One-time, local-only setup so GitHub Actions can log in to Azure without a stored password.
# The lab's gh-secrets-setup.sh creates an app registration, but UTS blocks those for students,
# so this uses a user-assigned managed identity with a federated (OIDC) credential instead.
# Permissions are scoped to the deployment resource group only (least privilege).

export MSYS_NO_PATHCONV=1

IDENTITY_RG="${IDENTITY_RG:-kicklab-identity-rg}"
IDENTITY_NAME="${IDENTITY_NAME:-kicklab-github-oidc}"
RESOURCE_GROUP="${RESOURCE_GROUP:-kicklab-rg}"
LOCATION="${LOCATION:-australiaeast}"
BRANCHES="${BRANCHES:-main}"

echo "=== KICKLAB GitHub OIDC Identity Setup ==="

az account show >/dev/null 2>&1 || az login
gh auth status >/dev/null 2>&1 || gh auth login

SUBSCRIPTION_ID=$(az account show --query id -o tsv)
TENANT_ID=$(az account show --query tenantId -o tsv)

# Register resource providers here, once, so the GitHub identity doesn't need subscription-level rights
echo "Registering resource providers (skips if already registered)..."
for NAMESPACE in Microsoft.App Microsoft.OperationalInsights Microsoft.ContainerRegistry Microsoft.ManagedIdentity; do
  az provider register --namespace "$NAMESPACE" --wait
done

echo "Creating resource groups (safe to re-run)..."
az group create --name "$IDENTITY_RG" --location "$LOCATION" -o none
az group create --name "$RESOURCE_GROUP" --location "$LOCATION" -o none

if ! az identity show --resource-group "$IDENTITY_RG" --name "$IDENTITY_NAME" >/dev/null 2>&1; then
  az identity create --resource-group "$IDENTITY_RG" --name "$IDENTITY_NAME" -o none
  echo "Created managed identity $IDENTITY_NAME."
else
  echo "Found existing managed identity $IDENTITY_NAME."
fi

CLIENT_ID=$(az identity show --resource-group "$IDENTITY_RG" --name "$IDENTITY_NAME" --query clientId -o tsv)
PRINCIPAL_ID=$(az identity show --resource-group "$IDENTITY_RG" --name "$IDENTITY_NAME" --query principalId -o tsv)

# GitHub's OIDC subject has two possible formats; trust both so login works either way
REPO_SLUG=$(gh repo view --json nameWithOwner -q .nameWithOwner)
OWNER_NAME="${REPO_SLUG%%/*}"
REPO_NAME="${REPO_SLUG##*/}"
OWNER_ID=$(gh api "repos/${REPO_SLUG}" --jq '.owner.id')
REPO_ID=$(gh api "repos/${REPO_SLUG}" --jq '.id')

for BRANCH in $BRANCHES; do
  SAFE_BRANCH=$(echo "$BRANCH" | tr -c 'a-zA-Z0-9-\n' '-')
  for FORMAT in ids names; do
    if [[ "$FORMAT" == "ids" ]]; then
      SUBJECT="repo:${OWNER_NAME}@${OWNER_ID}/${REPO_NAME}@${REPO_ID}:ref:refs/heads/${BRANCH}"
    else
      SUBJECT="repo:${REPO_SLUG}:ref:refs/heads/${BRANCH}"
    fi
    CRED_NAME="github-${SAFE_BRANCH}-${FORMAT}"

    if az identity federated-credential show --name "$CRED_NAME" --identity-name "$IDENTITY_NAME" \
         --resource-group "$IDENTITY_RG" >/dev/null 2>&1; then
      az identity federated-credential update --name "$CRED_NAME" --identity-name "$IDENTITY_NAME" \
        --resource-group "$IDENTITY_RG" --issuer "https://token.actions.githubusercontent.com" \
        --subject "$SUBJECT" --audiences "api://AzureADTokenExchange" -o none
      echo "Synced federated credential $CRED_NAME -> $SUBJECT"
    else
      az identity federated-credential create --name "$CRED_NAME" --identity-name "$IDENTITY_NAME" \
        --resource-group "$IDENTITY_RG" --issuer "https://token.actions.githubusercontent.com" \
        --subject "$SUBJECT" --audiences "api://AzureADTokenExchange" -o none
      echo "Created federated credential $CRED_NAME -> $SUBJECT"
    fi
  done
done

# Contributor manages resources; User Access Administrator lets deploy-azure.sh grant each app AcrPull.
# Both are scoped to the deployment resource group only.
SCOPE="/subscriptions/${SUBSCRIPTION_ID}/resourceGroups/${RESOURCE_GROUP}"
for ROLE in "Contributor" "User Access Administrator"; do
  for ATTEMPT in 1 2 3 4 5 6; do
    OUTPUT=$(az role assignment create --assignee-object-id "$PRINCIPAL_ID" \
      --assignee-principal-type ServicePrincipal --role "$ROLE" --scope "$SCOPE" -o none 2>&1) && {
      echo "Granted $ROLE on $RESOURCE_GROUP."; break; }
    if echo "$OUTPUT" | grep -qi "already exists"; then
      echo "$ROLE already assigned on $RESOURCE_GROUP."; break
    fi
    # A new identity can take a minute to become visible for role assignments
    echo "Waiting for identity to propagate before assigning $ROLE (attempt $ATTEMPT)..."
    sleep 15
    if [[ "$ATTEMPT" -eq 6 ]]; then echo "$OUTPUT" >&2; exit 1; fi
  done
done

gh secret set AZURE_SUBSCRIPTION_ID --body "$SUBSCRIPTION_ID"
gh secret set AZURE_TENANT_ID --body "$TENANT_ID"
gh secret set AZURE_CLIENT_ID --body "$CLIENT_ID"
echo "Pushed AZURE_SUBSCRIPTION_ID, AZURE_TENANT_ID and AZURE_CLIENT_ID to GitHub Actions secrets."

echo "=== Identity Setup Complete ==="