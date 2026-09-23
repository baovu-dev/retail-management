import asyncio
import json
import sys
from datetime import datetime, timezone

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

MCP_URL = "http://localhost:8100/mcp"


async def main(tool_name, args):
    async with streamablehttp_client(MCP_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            print("Registered tools:")
            for tool in tools.tools:
                print(f"  - {tool.name}: {tool.description}")

            print(f"\nCalling {tool_name} with {args}")
            print(f"executed_at: {datetime.now(timezone.utc).isoformat(timespec='seconds')}")
            result = await session.call_tool(tool_name, args)
            print(f"isError: {result.isError}")
            if result.structuredContent:
                print(json.dumps(result.structuredContent, indent=2))
            else:
                for block in result.content:
                    print(getattr(block, "text", block))


if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else "rating_summary"
    arguments = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {"product_id": 101}
    asyncio.run(main(name, arguments))