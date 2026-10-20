from unittest.mock import Mock

import pytest

from test_orders_mcp import load_file

checks = load_file("validation_checks_test", "scripts/orders/validation_checks.py")


def test_recorded_failure_sets_process_result():
    assert checks.result_exit_code([{"result": "PASS"}, {"result": "FAIL"}]) == 1
    assert checks.result_exit_code([{"result": "PASS"}]) == 0


def test_normal_mcp_requires_id_status_and_screen():
    payload = {"order_id": 13, "status": "PENDING", "source": "mcp", "tool": "get_order_status"}
    screen = "Order #13: PENDING · Source: MCP (get_order_status)"
    assert checks.mcp_success(200, payload, screen, 13, "PENDING")
    assert not checks.mcp_success(200, {**payload, "order_id": 14}, screen, 13, "PENDING")
    assert not checks.mcp_success(200, {**payload, "status": "CANCELLED"}, screen, 13, "PENDING")
    assert not checks.mcp_success(200, payload, "unavailable", 13, "PENDING")


@pytest.mark.parametrize("url,kind,blocked", [
    ("https://fonts.googleapis.com/css2", "stylesheet", True),
    ("https://images.example.test/image.jpg", "image", True),
    ("http://localhost:5000/login", "document", False),
    ("http://localhost:5000/api/orders/mcp-token", "fetch", False),
    ("http://localhost:5004/api/mcp/order-status", "fetch", False),
    ("http://host.docker.internal:11434/api/generate", "fetch", False),
    ("https://example.test/api", "fetch", False),
])
def test_only_external_static_assets_are_blocked(url, kind, blocked):
    route = Mock()
    route.request.url, route.request.resource_type = url, kind
    checks.route_resource(route)
    assert route.abort.called == blocked
    assert route.continue_.called != blocked
