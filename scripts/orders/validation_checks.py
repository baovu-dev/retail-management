"""Assertions and network policy shared by browser validation and offline tests."""
from urllib.parse import urlsplit


def result_exit_code(report):
    return 1 if any(item.get("result") == "FAIL" for item in report) else 0


def mcp_success(http_status, payload, screen, order_id, expected_status):
    expected_screen = f"Order #{order_id}: {expected_status} · Source: MCP (get_order_status)"
    return (http_status == 200 and type(payload.get("order_id")) is int
            and payload["order_id"] == order_id and payload.get("status") == expected_status
            and payload.get("source") == "mcp" and payload.get("tool") == "get_order_status"
            and screen.strip() == expected_screen)


def route_resource(route):
    # Only external static assets are blocked. Never intercept API/fetch calls.
    host = urlsplit(route.request.url).hostname
    local = host in {"localhost", "127.0.0.1", "::1", "host.docker.internal"}
    if not local and route.request.resource_type in {"image", "font", "stylesheet"}:
        route.abort()
    else:
        route.continue_()
