import asyncio
import json
import os
import time
from pathlib import Path

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from ollama_client import ask

MCP_URL = os.getenv("MCP_URL", "http://localhost:8100/mcp")
PROMPT_FILE = Path(__file__).resolve().parent.parent / "prompts" / "mcp_review_prompt.txt"

EXPECTED_TOOLS = {"rating_summary", "reviews_by_product", "flagged_reviews"}

# (description, tool, arguments, what a correct result looks like)
CHECKS = [
    ("Normal: rating summary for product 101", "rating_summary", {"product_id": 101},
     lambda r: r.get("review_count", 0) > 0 and r.get("average_rating") is not None),
    ("Normal: flagged reviews are all flagged", "flagged_reviews", {},
     lambda r: "flagged_reviews" in r and all(x.get("is_flagged") for x in r["flagged_reviews"])),
    ("Boundary: limit=1 returns at most 1 review", "reviews_by_product", {"product_id": 103, "limit": 1},
     lambda r: r.get("count", 99) <= 1),
    ("Empty: product with no reviews", "rating_summary", {"product_id": 1},
     lambda r: r.get("review_count") == 0),
    ("Boundary: invalid product_id is rejected", "rating_summary", {"product_id": -5},
     lambda r: "error" in r),
    ("Boundary: no write tool exists (read-only)", "delete_review", {"review_id": 1},
     lambda r: "error" in r),
]


def _extract(result):
    if result.isError:
        text = " ".join(getattr(b, "text", "") for b in result.content)
        return {"error": text or "tool error"}
    if result.structuredContent:
        return result.structuredContent
    try:
        return json.loads(result.content[0].text)
    except Exception:
        return {"text": str(result.content)}


def _root_cause(exc):
    while isinstance(exc, BaseExceptionGroup) and exc.exceptions:
        exc = exc.exceptions[0]
    return exc


async def _run_checks(stage):
    async with streamablehttp_client(MCP_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            registered = {t.name for t in tools.tools}
            stage("OBSERVE", f"Registered tools: {sorted(registered)}")

            results = []
            for description, tool, arguments, expectation in CHECKS:
                stage("ACT", f"Calling {tool} with {json.dumps(arguments)}")
                result = _extract(await session.call_tool(tool, arguments))
                try:
                    ok = bool(expectation(result))
                except Exception:
                    ok = False
                summary = json.dumps(result)[:120]
                stage("OBSERVE", f"{'PASS' if ok else 'FAIL'} - {description} -> {summary}")
                results.append((description, ok))
            return registered, results


def run(stage):
    stage("PLAN", f"{len(CHECKS)} checks against the shared MCP server at {MCP_URL}")

    try:
        registered, results = asyncio.run(_run_checks(stage))
    except Exception as exc:
        stage("ADAPT", f"MCP server unreachable ({_root_cause(exc)!r}), retrying once in 2s")
        time.sleep(2)
        try:
            registered, results = asyncio.run(_run_checks(stage))
        except Exception as exc:
            stage("ADAPT", f"FAIL: MCP server still unreachable ({_root_cause(exc)!r})")
            return False

    missing = EXPECTED_TOOLS - registered
    if missing:
        stage("OBSERVE", f"FAIL - expected tools not registered: {sorted(missing)}")

    passed_count = sum(1 for _, ok in results if ok)
    all_passed = passed_count == len(results) and not missing

    evidence = "\n".join(
        [f"Registered tools: {sorted(registered)}"]
        + [f"{'PASS' if ok else 'FAIL'}: {d}" for d, ok in results]
    )
    stage("ADAPT", "Asking Ollama to review the evidence")
    review, error = ask(PROMPT_FILE.read_text(encoding="utf-8").format(evidence=evidence))
    if error:
        stage("ADAPT", f"Review skipped (Ollama error: {error})")
    else:
        for line in review.splitlines():
            if line.strip():
                stage("REVIEW", line.strip())

    stage("ADAPT", f"{passed_count}/{len(results)} checks passed")
    return all_passed