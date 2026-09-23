from mcp.server.fastmcp import FastMCP
from tools.student1_reviews import get_rating_summary

mcp = FastMCP("KICKLAB Shared MCP", host="0.0.0.0", port=8100)


@mcp.tool()
def rating_summary(product_id: int) -> dict:
    """Return the review count and average rating for one KICKLAB product. Read-only."""
    return get_rating_summary(product_id)


if __name__ == "__main__":
    mcp.run(transport="streamable-http")