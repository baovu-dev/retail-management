import os

from mcp.server.fastmcp import FastMCP
from tools.student1_reviews import get_rating_summary, get_reviews_by_product, get_flagged_reviews
from tools.student4_orders import get_order_status as read_order_status

mcp = FastMCP("KICKLAB Shared MCP", host=os.getenv("MCP_HOST", "0.0.0.0"),
              port=int(os.getenv("MCP_PORT", "8100")))


@mcp.tool()
def get_order_status(order_id: int, access_token: str) -> dict:
    """Read one order's status using a short-lived shared-login token scoped to that order.

    The Orders API validates the signature, expiry and customer ownership (or staff role).
    Never supply or return customer details. No writes are supported.
    """
    return read_order_status(order_id, access_token)


@mcp.tool()
def rating_summary(product_id: int) -> dict:
    """Return the review count and average rating for one KICKLAB product. Read-only."""
    return get_rating_summary(product_id)


@mcp.tool()
def reviews_by_product(product_id: int, limit: int = 10) -> dict:
    """Return a list of reviews for a specific KICKLAB product. Read-only."""
    return get_reviews_by_product(product_id, limit)


@mcp.tool()
def flagged_reviews() -> dict:
    """Return a list of all flagged reviews. Read-only."""
    return get_flagged_reviews()


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
