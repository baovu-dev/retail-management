"""Verify short-lived, order-scoped capabilities issued by the shared login app."""
import os

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

TOKEN_SALT = "orders-mcp-status-v1"
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


def mcp_enabled():
    return os.getenv("MCP_ENABLED", "false").strip().lower() in ("1", "true", "yes", "on")
