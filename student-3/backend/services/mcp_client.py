import asyncio
import json
import os

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

MCP_URL = os.getenv(
    "MCP_URL",
    "http://localhost:8100/mcp"
)

async def _call_tool(name, arguments):
    async with streamablehttp_client(MCP_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()

            result = await session.call_tool(
                name,
                arguments
            )

            if result.isError:
                text = " ".join(
                    getattr(block, "text", "")
                    for block in result.content
                )

                return {
                    "error": text or "MCP tool returned an error"
                }

            if result.structuredContent:
                return result.structuredContent

            return json.loads(
                result.content[0].text
            )


def call_tool(name, arguments=None):
    return asyncio.run(
        _call_tool(
            name,
            arguments or {}
        )
    )