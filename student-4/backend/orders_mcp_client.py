"""Use the shared MCP server's Streamable HTTP transport, as in Student 1."""
import asyncio
import json
import os
from datetime import timedelta

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


async def _call_order_status(order_id, access_token):
    url = os.getenv("MCP_URL", "http://localhost:8100/mcp")
    async with streamablehttp_client(url, timeout=timedelta(seconds=10),
                                     sse_read_timeout=timedelta(seconds=15)) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool("get_order_status", {
                "order_id": order_id, "access_token": access_token,
            })
            if result.isError:
                raise ValueError("MCP tool execution failed")
            payload = result.structuredContent or json.loads(result.content[0].text)
            if not isinstance(payload, dict):
                raise ValueError("Invalid MCP response")
            return payload


def call_order_status(order_id, access_token):
    return asyncio.run(_call_order_status(order_id, access_token))
