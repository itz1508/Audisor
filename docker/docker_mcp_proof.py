"""Containerized acceptance proof for the Audisor MCP image.

Drives the built ``audisor-cli:local`` image (never the host installation) to prove:
  1. the exact ``scan`` CLI syntax reported by the image (``scan --help``);
  2. a read-only ``/workspace`` mount can be scanned with that exact syntax;
  3. the read-only mount rejects writes;
  4. all six MCP tools work over stdio against a read-only mounted repository;
  5. unknown MCP input properties are rejected (``isError``) and every tool
     input schema declares ``additionalProperties: false``.

The script prints a single JSON report to stdout and exits non-zero unless every
check passes. It performs NO mutation operation: the fixture repository is only
ever mounted read-only, and replay is expected to report ``unresolved`` because
the read-only mount keeps the original evidence intact.

Run (from ``audisor/backend`` so the ``mcp`` client library is available):
    uv run --with mcp python ../docker/docker_mcp_proof.py
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

IMAGE = os.environ.get("AUDISOR_IMAGE", "audisor-cli:local")
EXPECTED_TOOLS = {
    "audisor_scan",
    "audisor_inspect",
    "audisor_normalize",
    "audisor_validate",
    "audisor_replay",
    "audisor_trace",
}
HERE = Path(__file__).resolve().parent
FIXTURE_DIR = HERE / ".fixture" / "repo"


def _docker_host_path(path: Path) -> str:
    """Return a forward-slash absolute path for Docker Desktop volume mounts."""
    return str(path).replace("\\", "/")


def _run_docker(args: list[str], timeout: int = 120) -> dict:
    completed = subprocess.run(
        ["docker", *args], capture_output=True, text=True, timeout=timeout
    )
    return {
        "args": args,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def _create_fixture() -> None:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    (FIXTURE_DIR / "app.py").write_text(
        "API_KEY = 'example-only-secret'\n", encoding="utf-8"
    )


def _fixture_unchanged() -> bool:
    app = FIXTURE_DIR / "app.py"
    if not app.is_file():
        return False
    return app.read_text(encoding="utf-8") == "API_KEY = 'example-only-secret'\n"


def _result_json(result: object) -> dict:
    content = getattr(result, "content")
    text = getattr(content[0], "text")
    return json.loads(text)


def proof_scan_help() -> dict:
    result = _run_docker(["run", "--rm", IMAGE, "scan", "--help"])
    return {
        "command": f"docker run --rm {IMAGE} scan --help",
        "returncode": result["returncode"],
        "help_output": result["stdout"].strip(),
        "ok": result["returncode"] == 0 and "repository" in result["stdout"],
    }


def proof_readonly_scan() -> dict:
    mount = _docker_host_path(FIXTURE_DIR)
    visible = _run_docker(
        ["run", "--rm", "-v", f"{mount}:/workspace:ro", "--entrypoint", "sh", IMAGE,
         "-c", "test -f /workspace/app.py && echo visible"]
    )
    mount_visible = visible["returncode"] == 0 and "visible" in visible["stdout"]
    # Exact syntax confirmed by `scan --help`: positional repository + --json.
    scan = _run_docker(
        ["run", "--rm", "-v", f"{mount}:/workspace:ro", IMAGE, "scan", "/workspace", "--json"]
    )
    scan_payload = {}
    try:
        scan_payload = json.loads(scan["stdout"])
    except json.JSONDecodeError:
        scan_payload = {}
    scan_ok = scan["returncode"] == 0 and "findings" in scan_payload
    write_attempt = _run_docker(
        ["run", "--rm", "-v", f"{mount}:/workspace:ro", "--entrypoint", "sh", IMAGE,
         "-c", "touch /workspace/should_fail 2>&1"]
    )
    write_blocked = write_attempt["returncode"] != 0
    return {
        "mount": f"{mount}:/workspace:ro",
        "mount_visible": mount_visible,
        "scan_returncode": scan["returncode"],
        "scan_has_findings": scan_ok,
        "write_attempt_returncode": write_attempt["returncode"],
        "write_attempt_output": (write_attempt["stdout"] + write_attempt["stderr"]).strip(),
        "write_blocked": write_blocked,
        "ok": bool(mount_visible and scan_ok and write_blocked),
    }


async def _mcp_session() -> dict:
    mount = _docker_host_path(FIXTURE_DIR)
    params = StdioServerParameters(
        command="docker",
        args=["run", "-i", "--rm", "-v", f"{mount}:/workspace:ro", IMAGE],
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            tools = (await session.list_tools()).tools
            tool_names = {t.name for t in tools}

            schema_report = {}
            for t in tools:
                schema = t.inputSchema or {}
                schema_report[t.name] = schema.get("additionalProperties", "absent")
            all_schemas_strict = all(
                schema.get("additionalProperties") is False for t in tools
                if (schema := (t.inputSchema or {}))
            )

            scan = _result_json(
                await session.call_tool("audisor_scan", {"repository_root": "/workspace"})
            )
            valid_scan_ok = "findings" in scan

            inspection = _result_json(
                await session.call_tool(
                    "audisor_inspect",
                    {
                        "inspection_id": "docker-ro-001",
                        "repository_root": "/workspace",
                        "issue": "Remove hardcoded API key",
                    },
                )
            )
            valid_inspect_ok = inspection.get("artifact_type") == "audisor.inspection"

            secret_finding = next(
                item
                for item in inspection["scan_report"]["findings"]
                if item["type"] == "hardcoded_secret"
            )

            trace = _result_json(
                await session.call_tool("audisor_trace", {"inspection": inspection})
            )
            valid_trace_ok = trace.get("artifact_type") == "audisor.trace"

            statement = {
                "schema_version": "1.0.0",
                "statement_id": "docker-norm-001",
                "producer": {"kind": "codex", "label": "Codex"},
                "inspection_ref": {
                    "inspection_id": inspection["inspection_id"],
                    "manifest_sha256": inspection["manifest_sha256"],
                },
                "finding_ids": [secret_finding["id"]],
                "diagnosis": {
                    "hypotheses": [
                        {
                            "rank": 1,
                            "claim": "Hardcoded secret present in app.py",
                            "confidence": "likely",
                            "evidence_refs": [
                                {"kind": "scan_finding", "reference": secret_finding["id"]}
                            ],
                        }
                    ],
                    "reasoned_diagnosis": "Hardcoded secret in app.py",
                    "evidence_refs": [
                        {"kind": "scan_finding", "reference": secret_finding["id"]}
                    ],
                },
                "constraints": {
                    "explicit_constraints": ["Do not expose secrets"],
                    "prohibited_changes": [],
                },
                "repair_success_criteria": [
                    {"check": "audisor_scan", "expected_result": "No secret finding"}
                ],
                "one_shot": {"viable": True, "blocker": None},
            }
            normalization = _result_json(
                await session.call_tool(
                    "audisor_normalize",
                    {"inspection": inspection, "llm_statement": statement},
                )
            )
            valid_normalize_ok = (
                normalization.get("artifact_type") == "audisor.normalization_package"
                and "source_snapshot" not in normalization
            )

            evaluation = {
                "findings": [
                    {
                        "id": secret_finding["id"],
                        "status": "valid",
                        "closure": "Remove the hardcoded secret.",
                        "scope": {"include": ["app.py"], "exclude": []},
                        "success_criteria": ["No secret finding."],
                        "validator": "audisor_scan",
                    }
                ]
            }
            validation = _result_json(
                await session.call_tool(
                    "audisor_validate",
                    {"inspection": inspection, "evaluation": evaluation},
                )
            )
            valid_validate_ok = validation.get("artifact_type") == "audisor.validation"

            replay = _result_json(
                await session.call_tool(
                    "audisor_replay",
                    {"inspection": inspection, "validation": validation},
                )
            )
            # Read-only mount keeps the secret in place, so replay must report
            # "unresolved"; that outcome is itself proof the mount was not written.
            valid_replay_ok = (
                replay.get("artifact_type") == "audisor.replay_result"
                and replay.get("overall_replay_status") == "unresolved"
            )

            unknown_call = await session.call_tool(
                "audisor_scan",
                {"repository_root": "/workspace", "unexpected_field": "should-be-rejected"},
            )
            unknown_is_error = bool(getattr(unknown_call, "isError", False))

            return {
                "server_name": getattr(getattr(init, "serverInfo", None), "name", None),
                "protocol_version": getattr(init, "protocolVersion", None),
                "tools_listed": sorted(tool_names),
                "tool_surface_matches": tool_names == EXPECTED_TOOLS,
                "input_schema_additional_properties": schema_report,
                "all_schemas_additional_properties_false": all_schemas_strict,
                "valid_scan_ok": valid_scan_ok,
                "valid_inspect_ok": valid_inspect_ok,
                "valid_trace_ok": valid_trace_ok,
                "valid_normalize_ok": valid_normalize_ok,
                "valid_validate_ok": valid_validate_ok,
                "valid_replay_ok": valid_replay_ok,
                "replay_overall_status": replay.get("overall_replay_status"),
                "all_six_valid_calls_passed": bool(
                    valid_scan_ok
                    and valid_inspect_ok
                    and valid_trace_ok
                    and valid_normalize_ok
                    and valid_validate_ok
                    and valid_replay_ok
                ),
                "unknown_property_rejected": unknown_is_error,
            }


def main() -> int:
    _create_fixture()
    report: dict = {"image": IMAGE}
    report["scan_help"] = proof_scan_help()
    report["readonly_scan"] = proof_readonly_scan()
    report["mcp"] = asyncio.run(_mcp_session())
    report["fixture_unchanged_after_mcp"] = _fixture_unchanged()

    mcp = report["mcp"]
    report["all_checks_passed"] = bool(
        report["scan_help"]["ok"]
        and report["readonly_scan"]["ok"]
        and mcp["tool_surface_matches"]
        and mcp["all_schemas_additional_properties_false"]
        and mcp["all_six_valid_calls_passed"]
        and mcp["unknown_property_rejected"]
        and report["fixture_unchanged_after_mcp"]
    )
    print(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True))
    return 0 if report["all_checks_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
