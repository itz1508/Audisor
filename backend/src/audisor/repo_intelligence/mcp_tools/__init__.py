"""MCP tool definitions and dispatcher for repository intelligence.

Decomposed from mcp_server.py to enforce size policy.
"""

from .tools import TOOLS
from .dispatcher import dispatch

__all__ = ["TOOLS", "dispatch"]
