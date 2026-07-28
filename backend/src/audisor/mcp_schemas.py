"""Shared JSON Schema and payload helpers for the Audisor MCP server."""

from __future__ import annotations

from typing import Any


def strict_schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    """Build a strict JSON Schema that rejects unknown properties.

    The low-level MCP server validates call arguments against this schema with
    jsonschema; ``additionalProperties: False`` makes unknown properties a
    validation error instead of being silently dropped.
    """
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def blocked_payload(code: str, detail: str) -> dict[str, Any]:
    """Structured blocked-error payload shared by dispatch handlers."""
    return {"status": "blocked", "error": {"code": code, "detail": detail}}
