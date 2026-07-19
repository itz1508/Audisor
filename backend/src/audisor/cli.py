from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

from .artifacts import ArtifactError, read_json
from .contracts import ContractError, InspectionRequest
from .inspection import inspect_repository
from .replay import replay_inspection
from .scanner import scan_report
from .validation import validate_inspection


def _print(value: object, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(value, ensure_ascii=True, sort_keys=True))
    else:
        print(value)


def _install_codex() -> int:
    command = ["codex", "mcp", "add", "audisor", "--", sys.executable, "-m", "audisor.cli", "mcp"]
    try:
        completed = subprocess.run(command, check=False, capture_output=True, text=True)
    except FileNotFoundError:
        _print({"status": "blocked", "error": {"code": "codex_not_found", "detail": "Install Codex before registering Audisor."}}, as_json=True)
        return 3
    result = {
        "status": "completed" if completed.returncode == 0 else "failed",
        "command": command,
        "exit_code": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }
    _print(result, as_json=True)
    return completed.returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="audisor", description="Evidence-first issue inspection for Codex.")
    commands = parser.add_subparsers(dest="command", required=True)
    scan_command = commands.add_parser("scan", help="Create a deterministic ScanReport for one repository.")
    scan_command.add_argument("repository", type=Path)
    scan_command.add_argument("--baseline")
    scan_command.add_argument("--json", action="store_true")
    inspect_command = commands.add_parser("inspect", help="Capture immutable original issue evidence for later validation and replay.")
    inspect_command.add_argument("request_json", type=Path)
    inspect_command.add_argument("--json", action="store_true")
    validate_command = commands.add_parser("validate", help="Verify inspection evidence and a Codex Gap Evaluation.")
    validate_command.add_argument("inspection_json", type=Path)
    validate_command.add_argument("evaluation_json", type=Path)
    validate_command.add_argument("--json", action="store_true")
    replay_command = commands.add_parser("replay", help="Compare original inspected evidence with the current resolved repository.")
    replay_command.add_argument("inspection_json", type=Path)
    replay_command.add_argument("validation_json", type=Path)
    replay_command.add_argument("--json", action="store_true")
    mcp_command = commands.add_parser("mcp", help="Run Audisor as a stdio MCP server.")
    install_command = commands.add_parser("install-codex", help="Register the installed Audisor MCP server with Codex.")
    install_command.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "scan":
        if not args.repository.is_dir():
            _print({"status": "failed", "error": {"code": "repository_not_found", "detail": str(args.repository)}}, as_json=True)
            return 2
        _print(scan_report(args.repository, baseline=args.baseline).as_dict(), as_json=True)
        return 0
    if args.command == "inspect":
        try:
            request = InspectionRequest.from_mapping(read_json(args.request_json))
            _print(inspect_repository(request), as_json=True)
            return 0
        except (ArtifactError, ContractError) as exc:
            _print({"status": "failed", "error": {"code": "invalid_inspection_request", "detail": str(exc)}}, as_json=True)
            return 2
    if args.command == "validate":
        try:
            _print(validate_inspection(read_json(args.inspection_json), read_json(args.evaluation_json)), as_json=True)
            return 0
        except ArtifactError as exc:
            _print({"status": "blocked", "error": {"code": "validation_blocked", "detail": str(exc)}}, as_json=True)
            return 3
    if args.command == "replay":
        try:
            _print(replay_inspection(read_json(args.inspection_json), read_json(args.validation_json)), as_json=True)
            return 0
        except ArtifactError as exc:
            _print({"status": "blocked", "error": {"code": "replay_blocked", "detail": str(exc)}}, as_json=True)
            return 3
    if args.command == "mcp":
        from .mcp_server import main as mcp_main

        mcp_main()
        return 0
    if args.command == "install-codex":
        return _install_codex()
if __name__ == "__main__":
    raise SystemExit(main())
