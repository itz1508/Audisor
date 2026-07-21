"""Clean-installed MCP proof script.

Builds current 0.2.0 wheel, installs non-editably into a fresh venv outside the repo,
and executes all CLI help routes + full MCP stdio lifecycle from outside the source tree.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def _test_installed_mcp(python_bin: Path, audisor_bin: Path, test_dir: Path) -> dict:
    repo = test_dir / "target_repo"
    repo.mkdir()
    (repo / "app.py").write_text("x = 1\n", encoding="utf-8")

    params = StdioServerParameters(command=str(audisor_bin), args=["mcp"])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            tools = (await session.list_tools()).tools
            tool_names = sorted(t.name for t in tools)

            scan = getattr(
                await session.call_tool("audisor_scan", {"repository_root": str(repo)}),
                "content",
            )[0].text
            scan_data = json.loads(scan)
            valid_scan_ok = "findings" in scan_data

            unknown_call = await session.call_tool(
                "audisor_scan",
                {"repository_root": str(repo), "unexpected_field": "reject-me"},
            )
            unknown_rejected = bool(getattr(unknown_call, "isError", False))

            return {
                "server_name": getattr(init.serverInfo, "name", None),
                "tools_listed": tool_names,
                "tools_count": len(tool_names),
                "valid_scan_ok": valid_scan_ok,
                "unknown_property_rejected": unknown_rejected,
            }


def main() -> int:
    # Derive the backend directory from this file's location so the proof is
    # portable across machines (no hardcoded host paths).
    backend_dir = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        venv_dir = tmp_path / "venv"
        subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)

        python_bin = venv_dir / ("Scripts" if sys.platform == "win32" else "bin") / "python.exe"
        audisor_bin = venv_dir / ("Scripts" if sys.platform == "win32" else "bin") / "audisor.exe"

        wheel = backend_dir / "dist" / "audisor_local-0.2.0-py3-none-any.whl"
        if not wheel.is_file():
            subprocess.run(["uv", "build"], cwd=str(backend_dir), check=True)

        subprocess.run([str(python_bin), "-m", "pip", "install", str(wheel)], check=True)

        # 1. Import resolves to site-packages
        res = subprocess.run(
            [str(python_bin), "-c", "import audisor; print(audisor.__file__)"],
            capture_output=True,
            text=True,
            check=True,
            cwd=str(tmp_path),
        )
        imported_path = res.stdout.strip().replace("\\", "/")
        backend_forward = str(backend_dir).replace("\\", "/")
        resolves_to_site_packages = "site-packages" in imported_path and backend_forward not in imported_path

        # 2. CLI --help
        res = subprocess.run([str(audisor_bin), "--help"], capture_output=True, text=True, cwd=str(tmp_path))
        cli_help_ok = res.returncode == 0 and "Evidence-first issue inspection" in res.stdout

        # 3. All command help routes
        cmds = ["scan", "inspect", "trace", "normalize", "validate", "replay", "mcp", "install-codex"]
        command_helps = {}
        for cmd in cmds:
            res = subprocess.run([str(audisor_bin), cmd, "--help"], capture_output=True, text=True, cwd=str(tmp_path))
            command_helps[cmd] = res.returncode == 0

        all_command_helps_ok = all(command_helps.values())

        # 4. Installed MCP stdio execution
        mcp_report = asyncio.run(_test_installed_mcp(python_bin, audisor_bin, tmp_path))

        executables_from_clean_env = (
            str(python_bin.resolve()).startswith(str(venv_dir.resolve()))
            and str(audisor_bin.resolve()).startswith(str(venv_dir.resolve()))
        )

        report = {
            "imported_module_path": imported_path,
            "resolves_to_site_packages": resolves_to_site_packages,
            "cli_help_ok": cli_help_ok,
            "all_command_helps_ok": all_command_helps_ok,
            "command_helps_detail": command_helps,
            "mcp_server_name": mcp_report["server_name"],
            "mcp_tools_listed": mcp_report["tools_listed"],
            "mcp_tools_count_is_six": mcp_report["tools_count"] == 6,
            "mcp_valid_scan_ok": mcp_report["valid_scan_ok"],
            "mcp_unknown_property_rejected": mcp_report["unknown_property_rejected"],
            "executables_from_clean_env": executables_from_clean_env,
            "clean_shutdown": True,
        }

        report["all_checks_passed"] = bool(
            report["resolves_to_site_packages"]
            and report["cli_help_ok"]
            and report["all_command_helps_ok"]
            and report["mcp_tools_count_is_six"]
            and report["mcp_valid_scan_ok"]
            and report["mcp_unknown_property_rejected"]
            and report["executables_from_clean_env"]
        )

        print(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True))
        return 0 if report["all_checks_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
