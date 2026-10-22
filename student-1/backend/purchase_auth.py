"""Verify product-bound customer proofs; never authorize Orders CRUD or staff actions."""
import os

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

SALT = "orders-verified-purchase-v1"  # noqa: S105 - public signing-domain separator
AUDIENCE = "orders-verified-purchase"
SCOPE = "reviews:purchase"


def positive_id(value):
    return type(value) is int and 0 < value <= 2147483647


def purchase_key_ready():
    secret = os.getenv("ORDERS_PURCHASE_SECRET", "")
    return len(secret) >= 32 and secret not in {
        os.getenv("ORDERS_CRUD_SECRET", ""), os.getenv("ORDERS_MCP_SECRET", "")}


def verify_purchase_proof(token, product_id):
    if not purchase_key_ready():
        return None, ({"error": "Purchase verification is not configured.", "code": "unavailable"}, 503)
    if not isinstance(token, str) or not token or len(token) > 4096:
        return None, ({"error": "Customer purchase proof required.", "code": "unauthorized"}, 401)
    try:
        claims = URLSafeTimedSerializer(os.environ["ORDERS_PURCHASE_SECRET"], salt=SALT).loads(token, max_age=120)
    except (BadSignature, SignatureExpired, TypeError, ValueError):
        return None, ({"error": "Purchase proof invalid or expired.", "code": "unauthorized"}, 401)
    if (not isinstance(claims, dict) or claims.get("aud") != AUDIENCE or claims.get("scope") != SCOPE
            or claims.get("iss") != "kicklab-shared" or claims.get("role") != "customer"
            or not positive_id(claims.get("customer_id")) or not positive_id(claims.get("product_id"))):
        return None, ({"error": "Invalid purchase proof scope.", "code": "unauthorized"}, 401)
    if not positive_id(product_id) or claims["product_id"] != product_id:
        return None, ({"error": "Proof does not permit this product.", "code": "forbidden"}, 403)
    return claims, None
