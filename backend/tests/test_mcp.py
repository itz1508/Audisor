from __future__ import annotations

import asyncio
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from audisor.cli import _install_codex


def _result_json(result: object) -> dict[str, object]:
    content = getattr(result, "content")
    text = getattr(content[0], "text")
    return json.loads(text)


class McpServerTests(unittest.TestCase):
    def test_stdio_server_lists_and_calls_the_canonical_tools(self) -> None:
        asyncio.run(self._stdio_server_smoke())

    async def _stdio_server_smoke(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "app.py").write_text("API_KEY = 'example-only-secret'\n", encoding="utf-8")
            parameters = StdioServerParameters(command=sys.executable, args=["-m", "audisor.cli", "mcp"])
            async with stdio_client(parameters) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tool_names = {tool.name for tool in (await session.list_tools()).tools}
                    self.assertEqual(tool_names, {"audisor_scan", "audisor_inspect", "audisor_validate", "audisor_replay"})
                    scan = _result_json(await session.call_tool("audisor_scan", {"repository_root": str(root)}))
                    self.assertIn("findings", scan)
                    inspection = _result_json(
                        await session.call_tool(
                            "audisor_inspect",
                            {"inspection_id": "mcp-smoke", "repository_root": str(root), "issue": "Remove the hardcoded test secret."},
                        )
                    )
                    self.assertEqual(inspection["artifact_type"], "audisor.inspection")
                    evaluation = {"findings": []}
                    for finding in inspection["scan_report"]["findings"]:
                        if finding["type"] == "hardcoded_secret":
                            evaluation["findings"].append(
                                {
                                    "id": finding["id"],
                                    "status": "valid",
                                    "closure": "Remove the hardcoded secret.",
                                    "scope": {"include": ["app.py"], "exclude": []},
                                    "success_criteria": ["No hardcoded secret signal remains."],
                                    "validator": "audisor_scan",
                                }
                            )
                        else:
                            evaluation["findings"].append({"id": finding["id"], "status": "not_valid"})
                    validation = _result_json(await session.call_tool("audisor_validate", {"inspection": inspection, "evaluation": evaluation}))
                    self.assertEqual(validation["artifact_type"], "audisor.validation")
                    replay = _result_json(await session.call_tool("audisor_replay", {"inspection": inspection, "validation": validation}))
                    self.assertEqual(replay["artifact_type"], "audisor.replay_result")

    def test_install_codex_uses_the_public_bundle_command(self) -> None:
        completed = subprocess.CompletedProcess(["codex"], 0, stdout="registered", stderr="")
        with patch("audisor.cli.subprocess.run", return_value=completed) as run:
            self.assertEqual(_install_codex(), 0)
        run.assert_called_once_with(
            ["codex", "mcp", "add", "audisor", "--", sys.executable, "-m", "audisor.cli", "mcp"],
            check=False,
            capture_output=True,
            text=True,
        )

    def test_install_codex_reports_missing_codex(self) -> None:
        with patch("audisor.cli.subprocess.run", side_effect=FileNotFoundError):
            self.assertEqual(_install_codex(), 3)
