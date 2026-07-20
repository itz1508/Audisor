from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from audisor.artifacts import ArtifactError
from audisor.contracts import InspectionRequest
from audisor.inspection import inspect_repository
from audisor.normalization import normalize_inspection


def write(root: Path, relative: str, content: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def statement(inspection: dict) -> dict:
    finding = inspection["scan_report"]["findings"][0]
    evidence = {"kind": "scan_finding", "reference": finding["id"]}
    return {
        "schema_version": "1.0.0",
        "statement_id": "normalization-test-001",
        "producer": {"kind": "codex", "label": "Codex"},
        "inspection_ref": {"inspection_id": inspection["inspection_id"], "manifest_sha256": inspection["manifest_sha256"]},
        "finding_ids": [finding["id"]],
        "diagnosis": {
            "hypotheses": [{"rank": 1, "claim": "The parser confirms invalid syntax.", "confidence": "confirmed", "evidence_refs": [evidence]}],
            "reasoned_diagnosis": "The source cannot be imported until the syntax is corrected.",
            "evidence_refs": [evidence],
        },
        "constraints": {"explicit_constraints": ["Keep scope bounded."], "prohibited_changes": ["Do not edit unrelated files."]},
        "repair_success_criteria": [{"check": "python -m py_compile app.py", "expected_result": "Exit code 0."}],
        "one_shot": {"viable": True, "blocker": None},
    }


class NormalizeTests(unittest.TestCase):
    def inspect(self, root: Path) -> dict:
        write(root, "app.py", "def broken(:\n")
        return inspect_repository(InspectionRequest.from_mapping({"inspection_id": "normalize-001", "repository_root": str(root), "issue": "Fix app.py"}))

    def test_normalize_returns_only_referenced_context(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            inspection = self.inspect(Path(directory))
            package = normalize_inspection(inspection, statement(inspection))
        self.assertEqual(package["artifact_type"], "audisor.normalization_package")
        self.assertNotIn("source_snapshot", package)
        self.assertNotIn("replay", package)
        self.assertEqual(package["inspection_ref"]["manifest_sha256"], inspection["manifest_sha256"])

    def test_normalize_rejects_wrong_inspection_or_finding_reference(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            inspection = self.inspect(Path(directory))
            wrong_hash = statement(inspection)
            wrong_hash["inspection_ref"]["manifest_sha256"] = "b" * 64
            with self.assertRaises(ArtifactError):
                normalize_inspection(inspection, wrong_hash)
            unknown_finding = statement(inspection)
            unknown_finding["finding_ids"] = ["missing"]
            with self.assertRaises(ArtifactError):
                normalize_inspection(inspection, unknown_finding)

    def test_cli_normalize_smoke(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "repo"
            inspection = self.inspect(root)
            inspection_path = Path(directory) / "inspection.json"
            statement_path = Path(directory) / "statement.json"
            inspection_path.write_text(json.dumps(inspection), encoding="utf-8")
            statement_path.write_text(json.dumps(statement(inspection)), encoding="utf-8")
            result = subprocess.run([sys.executable, "-m", "audisor.cli", "normalize", str(inspection_path), str(statement_path), "--json"], capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout)["artifact_type"], "audisor.normalization_package")
