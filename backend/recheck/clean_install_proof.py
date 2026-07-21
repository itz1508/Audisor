"""Clean non-editable install proof for the standalone Audisor tool.

Builds a wheel, creates a fresh venv OUTSIDE the repository, installs
non-editable, then exercises: --version, --help, scan, MCP round trip
(initialize + tools/list + call), and install-codex registration.

Emits a single JSON object to stdout.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
import subprocess
import sys
import tempfile

BACKEND = Path(__file__).resolve().parent.parent  # audisor/backend


def _run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


async def _mcp_round_trip(python: str, repo_root: str) -> dict:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(command=python, args=["-m", "audisor.cli", "mcp"])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = (await session.list_tools()).tools
            tool_names = sorted(t.name for t in tools)
            result = await session.call_tool("audisor_scan", {"repository_root": repo_root})
            content = getattr(result, "content")
            payload = json.loads(getattr(content[0], "text"))
            return {"tools": tool_names, "scan_has_findings": "findings" in payload}


def main() -> int:
    checks: dict[str, object] = {}
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        dist = workspace / "dist"
        venv_dir = workspace / "venv"
        test_repo = workspace / "test-repo"
        test_repo.mkdir()
        (test_repo / "app.py").write_text("x = 1\n", encoding="utf-8")

        # 1. Build wheel
        build = _run(["uv", "build", "--wheel", "-o", str(dist)], cwd=str(BACKEND))
        wheels = list(dist.glob("*.whl")) if dist.exists() else []
        checks["wheel_built"] = build.returncode == 0 and len(wheels) == 1

        if not wheels:
            checks["error"] = f"wheel build failed: {build.stderr}"
            print(json.dumps({"checks": checks, "all_checks_passed": False}, indent=2, sort_keys=True))
            return 1

        # 2. Create fresh venv outside repo
        venv_create = _run([sys.executable, "-m", "venv", str(venv_dir)])
        venv_python = str(venv_dir / "Scripts" / "python.exe")
        checks["venv_created"] = venv_create.returncode == 0 and Path(venv_python).exists()

        # 3. Install non-editable
        install = _run(["uv", "pip", "install", "--python", venv_python, str(wheels[0])])
        checks["installed_non_editable"] = install.returncode == 0

        # 4. --version
        ver = _run([venv_python, "-m", "audisor.cli", "--version"])
        checks["version_ok"] = ver.returncode == 0 and "audisor-local" in ver.stdout

        # 5. --help
        help_proc = _run([venv_python, "-m", "audisor.cli", "--help"])
        checks["help_ok"] = help_proc.returncode == 0 and "scan" in help_proc.stdout

        # 6. scan
        scan_proc = _run([venv_python, "-m", "audisor.cli", "scan", str(test_repo), "--json"])
        scan_ok = False
        if scan_proc.returncode == 0:
            try:
                scan_data = json.loads(scan_proc.stdout)
                scan_ok = "findings" in scan_data
            except json.JSONDecodeError:
                pass
        checks["scan_ok"] = scan_ok

        # 7. MCP round trip from installed package
        try:
            mcp_result = asyncio.run(_mcp_round_trip(venv_python, str(test_repo)))
            expected_tools = ["audisor_inspect", "audisor_normalize", "audisor_replay", "audisor_scan", "audisor_trace", "audisor_validate"]
            checks["mcp_round_trip_ok"] = (
                mcp_result["tools"] == expected_tools and mcp_result["scan_has_findings"]
            )
        except Exception as exc:
            checks["mcp_round_trip_ok"] = False
            checks["mcp_error"] = str(exc)

        # 8. install-codex (registers with Codex; codex CLI is available)
        codex_proc = _run([venv_python, "-m", "audisor.cli", "install-codex", "--json"])
        codex_ok = False
        if codex_proc.returncode == 0:
            try:
                codex_data = json.loads(codex_proc.stdout)
                codex_ok = codex_data.get("status") == "completed"
            except json.JSONDecodeError:
                pass
        checks["install_codex_ok"] = codex_ok
        if not codex_ok:
            checks["install_codex_detail"] = codex_proc.stdout[:500] or codex_proc.stderr[:500]

        # 9. Ran outside repo
        checks["ran_outside_repo"] = not str(workspace).startswith(str(BACKEND))

    report = {"checks": checks, "all_checks_passed": all(bool(v) for k, v in checks.items() if k != "install_codex_detail" and k != "mcp_error" and k != "error")}
    print(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True))
    return 0 if report["all_checks_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
