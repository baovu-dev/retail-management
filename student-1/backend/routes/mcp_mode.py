import json
import os
from datetime import datetime, timezone

from flask import Blueprint, request
from markupsafe import escape

from services.mcp_client import call_tool

mcp_bp = Blueprint("mcp_mode", __name__)


def mcp_mode_is_enabled(req) -> bool:
    enabled = os.getenv("MCP_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on")
    if not enabled:
        return False
    mode_header = req.headers.get("X-MCP-Mode", "on").strip().lower()
    return mode_header in ("1", "true", "yes", "on")


def mcp_disabled_response():
    return "<p>MCP Mode is disabled.</p>", 403


def mcp_render_json(title, arguments, payload):
    executed_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return (
        f"<h3>{escape(title)}</h3>"
        f"<p>Input: {escape(json.dumps(arguments))}<br>Executed at: {executed_at}</p>"
        f"<pre>{escape(json.dumps(payload, indent=2))}</pre>"
    )


@mcp_bp.post("/mcp/rating-summary")
def mcp_rating_summary():
    if not mcp_mode_is_enabled(request):
        return mcp_disabled_response()

    raw = request.form.get("product_id", "").strip()
    if not raw.isdigit() or int(raw) <= 0:
        return "<p>product_id must be a positive number.</p>", 400

    arguments = {"product_id": int(raw)}
    try:
        result = call_tool("rating_summary", arguments)
        status = 400 if "error" in result else 200
        return mcp_render_json("MCP Tool: rating_summary", arguments, result), status
    except Exception as exc:
        error = {"error": "Shared MCP server unreachable", "detail": str(exc)}
        return mcp_render_json("MCP Tool: rating_summary", arguments, error), 503