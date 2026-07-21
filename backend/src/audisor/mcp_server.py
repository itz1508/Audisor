from __future__ import annotations

from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from .artifacts import ArtifactError
from .contracts import ContractError, InspectionRequest
from .inspection import inspect_repository
from .normalization import normalize_inspection
from .replay import replay_inspection
from .scanner import scan_report
from .trace import trace_inspection
from .validation import validate_inspection


def _error(code: str, detail: str) -> dict[str, Any]:
    return {"status": "blocked", "error": {"code": code, "detail": detail}}


def create_server() -> FastMCP:
    server = FastMCP(
        "Audisor",
        instructions="Read-only issue inspection, validation, and replay tools. Codex remains the only repair writer.",
        json_response=True,
    )

    @server.tool(name="audisor_scan")
    def audisor_scan(repository_root: str, baseline: str | None = None) -> dict[str, Any]:
        """Create a deterministic ScanReport for a repository without modifying it."""
        root = Path(repository_root)
        if not root.is_dir():
            return _error("repository_not_found", repository_root)
        return scan_report(root, baseline=baseline).as_dict()

    @server.tool(name="audisor_inspect")
    def audisor_inspect(
        inspection_id: str,
        repository_root: str,
        issue: str,
        baseline: str | None = None,
    ) -> dict[str, Any]:
        """Create immutable original-issue evidence and a safe source snapshot."""
        try:
            request = InspectionRequest.from_mapping(
                {
                    "inspection_id": inspection_id,
                    "repository_root": repository_root,
                    "issue": issue,
                    "baseline": baseline,
                }
            )
            return inspect_repository(request)
        except (ArtifactError, ContractError, ValueError) as exc:
            return _error("invalid_inspection_request", str(exc))

    @server.tool(name="audisor_normalize")
    def audisor_normalize(inspection: dict[str, Any], llm_statement: dict[str, Any]) -> dict[str, Any]:
        """Create a no-snapshot Normalize Package from Inspection, Dossier, Handoff, and an LLM Statement."""
        try:
            return normalize_inspection(inspection, llm_statement)
        except (ArtifactError, ValueError) as exc:
            return _error("normalization_blocked", str(exc))

    @server.tool(name="audisor_validate")
    def audisor_validate(inspection: dict[str, Any], evaluation: dict[str, Any]) -> dict[str, Any]:
        """Hash-lock inspection evidence and validate a complete Gap Evaluation before repair."""
        try:
            return validate_inspection(inspection, evaluation)
        except (ArtifactError, ValueError) as exc:
            return _error("validation_blocked", str(exc))

    @server.tool(name="audisor_replay")
    def audisor_replay(inspection: dict[str, Any], validation: dict[str, Any]) -> dict[str, Any]:
        """Compare original evidence with current source after Codex repairs it."""
        try:
            return replay_inspection(inspection, validation)
        except (ArtifactError, ValueError) as exc:
            return _error("replay_blocked", str(exc))

    @server.tool(name="audisor_trace")
    def audisor_trace(inspection: dict[str, Any]) -> dict[str, Any]:
        """Trace static parents, entrypoints, and direct tests from immutable inspection evidence."""
        try:
            return trace_inspection(inspection)
        except ArtifactError as exc:
            return _error("trace_blocked", str(exc))

    for tool in server._tool_manager.list_tools():
        tool.fn_metadata.arg_model.model_config["extra"] = "forbid"
        tool.fn_metadata.arg_model.model_rebuild(force=True)
        tool.parameters = tool.fn_metadata.arg_model.model_json_schema(by_alias=True)

    return server


def main() -> None:
    create_server().run(transport="stdio")
