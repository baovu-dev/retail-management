"""Render one Azure Container App spec from a line of apps.conf.

A spec file avoids passing start commands such as sh -c "cd database && ..."
through az CLI arguments, which mangles them. JSON is valid YAML, so the spec
is written as JSON and read with `az containerapp create --yaml`.
"""
import json
import os
import shlex
import sys

APPS_FILE, APP_NAME = sys.argv[1], sys.argv[2]

ENV_DOMAIN = os.environ["ENV_DOMAIN"]
LOGIN_SERVER = os.environ["LOGIN_SERVER"]
IMAGE_TAG = os.environ["IMAGE_TAG"]
ENV_ID = os.environ["ENV_ID"]
PULL_ID = os.environ["PULL_ID"]
LOCATION = os.environ["LOCATION"]
MIN_REPLICAS = int(os.getenv("MIN_REPLICAS", "0"))

# Cloud baseline: every AI service is switched off (no Ollama, MCP, RAG or Multi-Agent server in Azure)
AI_OFF = {
    "AI_MODE_ENABLED": "false",
    "AI_ENABLED": "false",
    "MCP_ENABLED": "false",
    "RAG_ENABLED": "false",
    "MULTI_AGENT_ENABLED": "false",
}


def load_apps():
    apps = {}
    with open(APPS_FILE, encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            name, image, port, ingress, command = (line.split("|") + [""])[:5]
            apps[name] = {"image": image, "port": int(port), "ingress": ingress, "command": command}
    return apps


APPS = load_apps()


def url(name):
    """Container Apps addresses are predictable once the environment domain is known.
    This is an express environment, so internal apps use the same <app>.<domain> address
    style as public ones (just unreachable from the internet). That keeps every call on
    HTTPS, and the environment's wildcard certificate covers all of them."""
    return f"https://{name}.{ENV_DOMAIN}"


# Per-app settings, copied from docker-compose.yml with cloud addresses instead of localhost
APP_ENV = {
    "shared-backend": {
        "REVIEWS_API": url("student1-backend"),
        "PRODUCTS_API": url("student2-backend"),
        "CUSTOMERS_API": url("student3-backend"),
        "ORDERS_API": url("student4-backend"),
        "APP_ENV": "cloud",
        "STAFF_EMAIL": os.getenv("STAFF_EMAIL", "admin@kicklab.com"),
        "ORDERS_FRONTEND_ORIGIN": url("student4-frontend"),
        "CUSTOMERS_FRONTEND_ORIGIN": url("student3-backend"),
        "REVIEWS_FRONTEND_ORIGIN": url("student1-backend"),
        "REVIEWS_UI_URL": url("student1-backend"),
        "PRODUCTS_UI_URL": url("student2-frontend"),
        "CUSTOMERS_UI_URL": url("student3-backend"),
        "ORDERS_UI_URL": url("student4-frontend"),
        "CHATBOT_UI_URL": url("student5-frontend"),
    },
    "student1-backend": {
        "APP_ENV": "cloud",
        "DATABASE_URL": url("student1-database"),
        "SHARED_URL": url("shared-backend"),
        "PRODUCTS_URL": url("student2-frontend"),
        "ORDERS_UI_URL": url("student4-frontend"),
        "CHATBOT_URL": url("student5-frontend"),
        "ORDERS_API_URL": url("student4-backend"),
    },
    "student2-backend": {"DATABASE_URL": url("student2-database")},
    "student2-frontend": {"API_BASE": url("student2-backend")},
    "student3-backend": {"DATABASE_URL": url("student3-database"), "SHARED_URL": url("shared-backend")},
    "student4-database": {"ORDERS_DB_PATH": "/app/data/orders.db"},
    "student4-backend": {"DATABASE_URL": url("student4-database"), "APP_ENV": "cloud",
                         "ORDERS_FRONTEND_ORIGIN": url("student4-frontend")},
    "student4-frontend": {"API_BASE": url("student4-backend"), "SHARED_BASE": url("shared-backend")},
    "student5-backend": {"DATABASE_URL": url("student5-database")},
    "student5-frontend": {"API_BASE": url("student5-backend")},
}

# Sensitive values are stored as Container Apps secrets, never as plain environment variables
APP_SECRETS = {
    "student1-backend": {"ORDERS_PURCHASE_SECRET": "orders-purchase-secret"},  # pragma: allowlist secret - reference name only
    "shared-backend": {"SECRET_KEY": "secret-key",  # pragma: allowlist secret - secret name, not a value
                       "STAFF_PASSWORD": "staff-password",  # pragma: allowlist secret - secret name, not a value
                       "ORDERS_MCP_SECRET": "orders-mcp-secret",  # pragma: allowlist secret - Container Apps secret name only
                       "ORDERS_CRUD_SECRET": "orders-crud-secret",  # pragma: allowlist secret - reference name only
                       "ORDERS_PURCHASE_SECRET": "orders-purchase-secret",  # pragma: allowlist secret - secret name, not a value
                       "CUSTOMERS_REVIEW_SECRET": "customers-review-secret"},  # pragma: allowlist secret - reference name only
    "student3-backend": {"CUSTOMERS_REVIEW_SECRET": "customers-review-secret"},  # pragma: allowlist secret - reference name only
    "student4-backend": {"ORDERS_MCP_SECRET": "orders-mcp-secret",  # pragma: allowlist secret - Container Apps secret name only
                       "ORDERS_CRUD_SECRET": "orders-crud-secret",  # pragma: allowlist secret - reference name only
                       "ORDERS_PURCHASE_SECRET": "orders-purchase-secret"},  # pragma: allowlist secret - secret name, not a value
}


def build_spec(name):
    app = APPS[name]
    secrets = APP_SECRETS.get(name, {})

    env = [{"name": key, "value": value} for key, value in {**AI_OFF, **APP_ENV.get(name, {})}.items()]
    env += [{"name": env_name, "secretRef": secret_name} for env_name, secret_name in secrets.items()]

    container = {
        "name": name,
        "image": f"{LOGIN_SERVER}/{app['image']}:{IMAGE_TAG}",
        "env": env,
        "resources": {"cpu": 0.25, "memory": "0.5Gi"},
    }
    if app["command"]:
        container["command"] = shlex.split(app["command"])

    return {
        "location": LOCATION,
        "identity": {"type": "UserAssigned", "userAssignedIdentities": {PULL_ID: {}}},
        "properties": {
            "managedEnvironmentId": ENV_ID,
            "configuration": {
                "activeRevisionsMode": "Single",
                "ingress": {
                    "external": app["ingress"] == "external",
                    "targetPort": app["port"],
                    "transport": "auto",
                    "allowInsecure": False,
                },
                "registries": [{"server": LOGIN_SERVER, "identity": PULL_ID}],
                "secrets": [{"name": secret_name, "value": os.environ[env_name]}
                            for env_name, secret_name in secrets.items()],
            },
            "template": {
                "containers": [container],
                # SQLite databases can't be shared between copies, so every app runs at most one
                "scale": {"minReplicas": MIN_REPLICAS, "maxReplicas": 1},
            },
        },
    }


print(json.dumps(build_spec(APP_NAME), indent=2))
