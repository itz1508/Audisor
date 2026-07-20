from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def _run(command: list[str], repository: Path) -> dict[str, object]:
    async with stdio_client(StdioServerParameters(command=command[0], args=command[1:])) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            result = await session.call_tool("audisor_scan", {"repository_root": str(repository)})
    return {"tools": sorted(tool.name for tool in tools.tools), "scan_result_count": len(result.content)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke an Audisor stdio MCP command.")
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        raise SystemExit("mcp_command_required")
    result = asyncio.run(_run(command, args.repository.resolve()))
    expected = {"audisor_scan", "audisor_inspect", "audisor_normalize", "audisor_trace", "audisor_validate", "audisor_replay"}
    if set(result["tools"]) != expected:
        raise SystemExit("unexpected_tool_surface")
    print(json.dumps({"status": "completed", **result}, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
