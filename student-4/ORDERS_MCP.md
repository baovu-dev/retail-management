# Orders MCP

Use the [Orders runbook](README.md) for setup, login, shared secrets and service
startup. The single shared host MCP server registers `get_order_status`.

Flow: Orders UI → shared-login scoped token → Orders backend
`POST /api/mcp/order-status` → host MCP tool → Orders authenticated internal lookup.
The tool is read-only. Customer ownership, staff role, token signature, expiry
and order scope are checked; request-supplied customer IDs do not establish identity.

[Retained MCP browser and agentic results](evidence/README.md) describe actual
historical executions. [Validation scripts](../scripts/orders/README.md) explain
which checks need private fixtures. Never commit tokens or runtime credentials.
