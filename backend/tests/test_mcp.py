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
from PIL import Image

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
            Image.new("RGB", (8, 8), (0, 0, 0)).save(root / "screen.png", format="PNG")
            parameters = StdioServerParameters(command=sys.executable, args=["-m", "audisor.cli", "mcp"])
            async with stdio_client(parameters) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tool_names = {tool.name for tool in (await session.list_tools()).tools}
                    # Original tools plus new repository intelligence tools
                    expected_tools = {
                        "audisor_scan", "audisor_inspect", "audisor_normalize",
                        "audisor_validate", "audisor_replay", "audisor_trace",
                        "repo_status", "repo_tree", "index_repository", "index_status",
                        "search_text", "read_file_range", "read_file_outline",
                        "list_symbols", "find_symbol", "find_references", "find_imports",
                        "dependency_neighbourhood", "git_status", "git_diff", "git_history",
                        "git_show_file", "run_command", "run_validation", "operation_status",
                        "refresh_paths", "operation_result",
                        "parse_test_failures", "parse_python_traceback", "summarise_command_failure",
                        "prepare_patch", "apply_patch",
                        "create_gap", "find_gap", "gap_record",
                    }
                    self.assertEqual(tool_names, expected_tools)
                    scan = _result_json(await session.call_tool("audisor_scan", {"repository_root": str(root)}))
                    self.assertIn("findings", scan)
                    inspection = _result_json(
                        await session.call_tool(
                            "audisor_inspect",
                            {"inspection_id": "mcp-smoke", "repository_root": str(root), "issue": "Remove the hardcoded test secret."},
                        )
                    )
                    self.assertEqual(inspection["artifact_type"], "audisor.inspection")
                    secret = next(item for item in inspection["scan_report"]["findings"] if item["type"] == "hardcoded_secret")
                    statement = {
                        "schema_version": "1.0.0",
                        "statement_id": "mcp-normalize-001",
                        "producer": {"kind": "codex", "label": "Codex"},
                        "inspection_ref": {"inspection_id": inspection["inspection_id"], "manifest_sha256": inspection["manifest_sha256"]},
                        "finding_ids": [secret["id"]],
                        "diagnosis": {"hypotheses": [{"rank": 1, "claim": "Key-shaped assignment requires review.", "confidence": "likely", "evidence_refs": [{"kind": "scan_finding", "reference": secret["id"]}]}], "reasoned_diagnosis": "The scanner found a key-shaped assignment.", "evidence_refs": [{"kind": "scan_finding", "reference": secret["id"]}]},
                        "constraints": {"explicit_constraints": ["Do not expose the value."], "prohibited_changes": ["Do not auto-rotate credentials."]},
                        "repair_success_criteria": [{"check": "audisor scan <repo> --json", "expected_result": "No hardcoded_secret signal remains."}],
                        "one_shot": {"viable": True, "blocker": None},
                    }
                    normalization = _result_json(await session.call_tool("audisor_normalize", {"inspection": inspection, "llm_statement": statement}))
                    self.assertEqual(normalization["artifact_type"], "audisor.normalization_package")
                    self.assertNotIn("source_snapshot", normalization)
                    trace = _result_json(await session.call_tool("audisor_trace", {"inspection": inspection}))
                    self.assertEqual(trace["artifact_type"], "audisor.trace")
                    evaluation = {"findings": []}
                    for finding in inspection["scan_report"]["findings"]:
                        if finding["type"] == "hardcoded_secret":
                            evaluation["findings"].append(
                                {
                                    "id": finding["id"],
                                    "status": "valid",
                                    "closure": "Remove the hardcoded secret.",
                                    "scope": {"include": ["app.py", "screen.png"], "exclude": []},
                                    "success_criteria": ["No hardcoded secret signal remains."],
                                    "validator": "audisor_scan",
                                }
                            )
                        else:
                            evaluation["findings"].append({"id": finding["id"], "status": "not_valid"})
                    validation = _result_json(await session.call_tool("audisor_validate", {"inspection": inspection, "evaluation": evaluation}))
                    self.assertEqual(validation["artifact_type"], "audisor.validation")
                    (root / "app.py").write_text("value = 1\n", encoding="utf-8")
                    Image.new("RGB", (8, 8), (255, 255, 255)).save(root / "screen.png", format="PNG")
                    replay = _result_json(await session.call_tool("audisor_replay", {"inspection": inspection, "validation": validation}))
                    self.assertEqual(replay["artifact_type"], "audisor.replay_result")
                    image_diff = next(item["image_diff"] for item in replay["diff_view"] if item["path"] == "screen.png")
                    self.assertEqual(image_diff["status"], "valid")

    def test_install_codex_uses_the_public_bundle_command(self) -> None:
        completed = subprocess.CompletedProcess(["codex"], 0, stdout="registered", stderr="")
        with patch("shutil.which", return_value="codex"), \
             patch("audisor.cli.subprocess.run", return_value=completed) as run:
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

    def test_unknown_property_is_rejected_at_runtime(self) -> None:
        """Prove that the MCP server rejects unknown input properties through a real
        stdio transport call, not merely by inspecting the JSON schema.

        This test is the pytest-collected regression proof required by the
        'MCP Input Schema Strictness' rule in Agents.md. It must remain here and
        must be re-run after any MCP SDK upgrade or tool-registration change.
        """
        asyncio.run(self._unknown_property_rejected())

    async def _unknown_property_rejected(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "app.py").write_text("x = 1\n", encoding="utf-8")
            parameters = StdioServerParameters(command=sys.executable, args=["-m", "audisor.cli", "mcp"])
            async with stdio_client(parameters) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()

                    # First confirm the schema advertises additionalProperties=false
                    tools = {t.name: t for t in (await session.list_tools()).tools}
                    scan_schema = tools["audisor_scan"].inputSchema
                    self.assertFalse(
                        scan_schema.get("additionalProperties", True),
                        "audisor_scan inputSchema must emit additionalProperties=false",
                    )

                    # Then prove the server actually rejects the unknown property at
                    # call time through the real transport — schema alone is not enough.
                    result = await session.call_tool(
                        "audisor_scan",
                        {"repository_root": str(root), "unknown_extra_field": "should_be_rejected"},
                    )
                    # The MCP SDK wraps tool errors as isError=True content,
                    # not as a raised exception on the client side.
                    self.assertTrue(
                        getattr(result, "isError", False),
                        "Server must return isError=True when an unknown property is passed; "
                        "got a successful result instead — unknown-property rejection is not enforced.",
                    )
