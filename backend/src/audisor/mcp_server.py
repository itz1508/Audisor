"""Audisor MCP server entry point.

Tool schemas live in ``mcp_tools_core``/``mcp_tools_ops``, dispatch handlers in
``mcp_dispatch_core``/``mcp_dispatch_ops``, and assembly in ``mcp_registration``.
"""

import json
from typing import Any

from importlib.metadata import version

import mcp.types as types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

from .mcp_registration import TOOLS, TOOL_INDEX, dispatch_tool
from .mcp_schemas import blocked_payload

# Backward-compatible names for the public tool contract.
_TOOLS = TOOLS
_TOOL_INDEX = TOOL_INDEX

_INSTRUCTIONS = (
    "Repository inspection, validation, replay, and intelligence tools. "
    "Codex remains the only repair writer."
)


def create_server() -> Server:
    server: Server = Server("Audisor", version=version("audisor-local"), instructions=_INSTRUCTIONS)

    @server.list_tools()
    async def handle_list_tools() -> list[types.Tool]:
        return TOOLS

    @server.call_tool()
    async def handle_call_tool(name: str, arguments: dict[str, Any] | None) -> list[types.TextContent]:
        if name not in TOOL_INDEX:
            payload = blocked_payload("invalid_request", f"Unknown tool: {name}")
        else:
            payload = dispatch_tool(name, arguments or {})
        return [types.TextContent(type="text", text=json.dumps(payload, ensure_ascii=True, sort_keys=True))]

    return server


def main() -> None:
    import anyio

    server = create_server()

    async def _run() -> None:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())

    anyio.run(_run)
