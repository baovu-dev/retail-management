"""Verify short-lived, order-scoped capabilities issued by the shared login app."""
import os

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

TOKEN_SALT = "orders-mcp-status-v1"  # noqa: S105 - public signing salt, not a secret
TOKEN_MAX_AGE = 120


def valid_order_id(value):
    return type(value) is int and 0 < value <= 2147483647


def verify_access_token(token, order_id):
    secret = os.getenv("ORDERS_MCP_SECRET", "")
    if len(secret) < 32:
        return None, ({"error": "Orders authentication is not configured.", "code": "unavailable"}, 503)
    if not isinstance(token, str) or not token or len(token) > 4096:
        return None, ({"error": "Valid shared login authentication is required.", "code": "unauthorized"}, 401)
    try:
        claims = URLSafeTimedSerializer(secret, salt=TOKEN_SALT).loads(token, max_age=TOKEN_MAX_AGE)
    except SignatureExpired:
        return None, ({"error": "Authentication expired. Please try again.", "code": "unauthorized"}, 401)
    except (BadSignature, TypeError, ValueError):
        return None, ({"error": "Valid shared login authentication is required.", "code": "unauthorized"}, 401)
    if not isinstance(claims, dict) or claims.get("aud") != "orders-mcp" or claims.get("scope") != "order:status":
        return None, ({"error": "Invalid authentication scope.", "code": "unauthorized"}, 401)
    if not valid_order_id(claims.get("order_id")) or claims["order_id"] != order_id:
        return None, ({"error": "Authentication does not permit this order.", "code": "forbidden"}, 403)
    if claims.get("role") == "customer" and valid_order_id(claims.get("customer_id")):
        return claims, None
    if claims.get("role") == "staff" and isinstance(claims.get("staff_email"), str) and claims["staff_email"]:
        return claims, None
    return None, ({"error": "Invalid authentication identity.", "code": "unauthorized"}, 401)


def bearer_token(req):
    scheme, _, value = req.headers.get("Authorization", "").partition(" ")
    return value if scheme.lower() == "bearer" else ""


def verify_review_token(token):
    """Review capabilities cannot be used as order-status capabilities."""
    secret = os.getenv("ORDERS_MCP_SECRET", "")
    if len(secret) < 32:
        return None, ({"error": "Orders authentication is not configured.", "code": "unavailable"}, 503)
    if not isinstance(token, str) or not token or len(token) > 4096:
        return None, ({"error": "Staff authentication is required.", "code": "unauthorized"}, 401)
    try:
        claims = URLSafeTimedSerializer(secret, salt="orders-multi-agent-v1").loads(token, max_age=TOKEN_MAX_AGE)
    except (SignatureExpired, BadSignature, TypeError, ValueError):
        return None, ({"error": "Staff authentication invalid or expired.", "code": "unauthorized"}, 401)
    if (not isinstance(claims, dict) or claims.get("aud") != "orders-multi-agent"
            or claims.get("scope") != "orders:workflow:review" or claims.get("role") != "staff"
            or not isinstance(claims.get("staff_email"), str) or not claims["staff_email"]):
        return None, ({"error": "Invalid review capability.", "code": "unauthorized"}, 401)
    return claims, None


def mcp_enabled():
    return os.getenv("MCP_ENABLED", "false").strip().lower() in ("1", "true", "yes", "on")


CRUD_SALT = "orders-crud-v1"  # noqa: S105 - public domain separation, not a credential
CRUD_AUDIENCE = "orders-crud"
CRUD_SCOPES = {"customer": "orders:customer:crud", "staff": "orders:staff:manage"}


def crud_configuration():
    from urllib.parse import urlsplit
    secret = os.getenv("ORDERS_CRUD_SECRET", "")
    origin = os.getenv("ORDERS_FRONTEND_ORIGIN", "http://localhost:3004")
    try:
        address = urlsplit(origin)
        valid_origin = (bool(address.hostname) and not address.username and not address.password
                        and not address.query and not address.fragment and address.path == ""
                        and (address.scheme == "https" or address.scheme == "http"
                             and address.hostname in {"localhost", "127.0.0.1"}))
    except ValueError:
        valid_origin = False
    cloud = os.getenv("APP_ENV", "local") == "cloud"
    return (len(secret) >= 32 and secret not in {os.getenv("ORDERS_MCP_SECRET", ""), os.getenv("ORDERS_PURCHASE_SECRET", "")} and valid_origin
            and (not cloud or "ORDERS_FRONTEND_ORIGIN" in os.environ and origin.startswith("https://")))


def verify_crud_token(token):
    if not crud_configuration():
        return None, ({"error": "Orders CRUD authentication is not configured.", "code": "unavailable"}, 503)
    if not isinstance(token, str) or not token or len(token) > 4096:
        return None, ({"error": "Orders login is required.", "code": "unauthorized"}, 401)
    try:
        claims = URLSafeTimedSerializer(os.environ["ORDERS_CRUD_SECRET"], salt=CRUD_SALT).loads(token, max_age=120)
    except (SignatureExpired, BadSignature, ValueError, TypeError):
        return None, ({"error": "Orders credential is invalid or expired.", "code": "unauthorized"}, 401)
    if (not isinstance(claims, dict) or claims.get("aud") != CRUD_AUDIENCE
            or claims.get("iss") != "kicklab-shared" or not isinstance(claims.get("role"), str) or claims["role"] not in CRUD_SCOPES
            or claims.get("scope") != CRUD_SCOPES[claims["role"]]):
        return None, ({"error": "Invalid Orders CRUD scope.", "code": "unauthorized"}, 401)
    if (claims["role"] == "customer" and valid_order_id(claims.get("customer_id"))
            or claims["role"] == "staff" and isinstance(claims.get("staff_email"), str) and claims["staff_email"].strip()):
        return claims, None
    return None, ({"error": "Invalid Orders identity.", "code": "unauthorized"}, 401)
