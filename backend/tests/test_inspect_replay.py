from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from audisor.artifacts import ArtifactError, verify_artifact
from audisor.contracts import InspectionRequest
from audisor.inspection import inspect_repository
from audisor.replay import replay_inspection
from audisor.validation import validate_inspection


def write(root: Path, relative: str, content: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def write_image(root: Path, relative: str, color: tuple[int, int, int]) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (16, 12), color).save(path, format="PNG")


def request(root: Path, issue: str = "Fix app.py") -> InspectionRequest:
    return InspectionRequest.from_mapping({"inspection_id": "inspect-001", "repository_root": str(root), "issue": issue})


def valid_evaluation(inspection: dict, path: str = "app.py") -> dict:
    finding = next(item for item in inspection["scan_report"]["findings"] if item["type"] == "syntax_error")
    return {"findings": [{
        "id": finding["id"], "status": "valid", "closure": "Correct the syntax error.",
        "scope": {"include": [path], "exclude": []}, "success_criteria": ["Python parses app.py."],
        "validator": "python -m py_compile app.py",
    }]}


class InspectValidateReplayTests(unittest.TestCase):
    def test_inspection_is_hashed_and_redacts_secret_values(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write(root, "app.py", 'API_KEY = "original-secret-value"\n')
            inspection = inspect_repository(request(root, 'Review API_KEY = "original-secret-value"'))
        verify_artifact(inspection, "audisor.inspection", "manifest_sha256")
        serialized = json.dumps(inspection)
        self.assertNotIn("original-secret-value", serialized)
        self.assertEqual(inspection["original_issue"], 'Review API_KEY = "[REDACTED]"')
        self.assertEqual(inspection["dossier"]["finding_ids"], [item["id"] for item in inspection["scan_report"]["findings"]])
        self.assertEqual(inspection["handoff"]["validation_hints"], ["hardcoded_secret"])

    def test_validation_blocks_stale_original_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write(root, "app.py", "def broken(:\n")
            inspection = inspect_repository(request(root))
            write(root, "app.py", "def fixed():\n    return 1\n")
            with self.assertRaises(ArtifactError):
                validate_inspection(inspection, valid_evaluation(inspection))

    def test_validation_locks_nested_requirements_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write(root, "service/requirements.txt", "requests==2\n")
            write(root, "service/app.py", "import requests\n")
            inspection = inspect_repository(request(root))
            self.assertIn("service/requirements.txt", {item["path"] for item in inspection["source_snapshot"]})
            write(root, "service/requirements.txt", "httpx==0.1\n")
            with self.assertRaises(ArtifactError):
                validate_inspection(inspection, {"findings": []})

    def test_replay_resolves_original_finding_and_shows_safe_diff(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write(root, "app.py", "def broken(:\n")
            inspection = inspect_repository(request(root))
            validation = validate_inspection(inspection, valid_evaluation(inspection))
            write(root, "app.py", "def fixed():\n    return 1\n")
            result = replay_inspection(inspection, validation)
        self.assertEqual(result["overall_replay_status"], "resolved")
        self.assertEqual(result["findings"][0]["replay_status"], "resolved")
        self.assertEqual(result["findings"][0]["validator_state"], "not_run")
        self.assertNotIn("result_sha256", result)
        self.assertIn("-def broken(:", result["diff_view"][0]["diff"])
        self.assertIn("+def fixed():", result["diff_view"][0]["diff"])

    def test_replay_marks_unchanged_issue_unresolved_and_deleted_scope_uncertain(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write(root, "app.py", "def broken(:\n")
            inspection = inspect_repository(request(root))
            validation = validate_inspection(inspection, valid_evaluation(inspection))
            unresolved = replay_inspection(inspection, validation)
            (root / "app.py").unlink()
            deleted = replay_inspection(inspection, validation)
        self.assertEqual(unresolved["findings"][0]["replay_status"], "unresolved")
        self.assertEqual(deleted["findings"][0]["replay_status"], "uncertainty")

    def test_replay_distinguishes_independent_findings_in_one_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write(root, "pyproject.toml", "[project]\nname = 'fixture'\nversion = '0'\n")
            write(root, "app.py", "import requests\nimport httpx\n")
            inspection = inspect_repository(request(root))
            dependency_findings = [item for item in inspection["scan_report"]["findings"] if item["type"] == "dependency_declaration_mismatch"]
            requests_finding = next(item for item in dependency_findings if item["evidence"]["module"] == "requests")
            evaluation = {"findings": [
                {"id": item["id"], "status": "valid", "closure": "Remove the requests import.", "scope": {"include": ["app.py"], "exclude": []}, "success_criteria": ["requests is no longer imported."], "validator": "audisor scan . --json"}
                if item["id"] == requests_finding["id"] else {"id": item["id"], "status": "not_valid"}
                for item in inspection["scan_report"]["findings"]
            ]}
            validation = validate_inspection(inspection, evaluation)
            write(root, "app.py", "import httpx\n")
            result = replay_inspection(inspection, validation)
        self.assertEqual(result["findings"][0]["replay_status"], "resolved")

    def test_replay_summarizes_unrelated_added_file_without_exposing_diff(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write(root, "app.py", "def broken(:\n")
            inspection = inspect_repository(request(root))
            validation = validate_inspection(inspection, valid_evaluation(inspection))
            write(root, "tests/test_new.py", "value = 1\n")
            result = replay_inspection(inspection, validation)
        self.assertEqual(result["diff_view"], [])
        self.assertEqual(result["unrelated_change_summary"], [{"path": "tests/test_new.py", "status": "added"}])

    def test_replay_keeps_git_drift_uncertain(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write(root, "app.py", "value = 1\n")
            subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.email", "tests@example.invalid"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.name", "Audisor Tests"], cwd=root, check=True)
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(["git", "commit", "-m", "baseline"], cwd=root, check=True, capture_output=True)
            write(root, "app.py", "value = 2\n")
            inspection = inspect_repository(InspectionRequest.from_mapping({"inspection_id": "drift-001", "repository_root": str(root), "issue": "Review drift", "baseline": "HEAD"}))
            finding = next(item for item in inspection["scan_report"]["findings"] if item["type"] == "repository_drift")
            evaluation = {"findings": [{"id": finding["id"], "status": "valid", "closure": "Confirm approved scope.", "scope": {"include": ["app.py"], "exclude": []}, "success_criteria": ["Baseline is refreshed."], "validator": "git diff --name-status HEAD"}]}
            validation = validate_inspection(inspection, evaluation)
            result = replay_inspection(inspection, validation)
        self.assertEqual(result["findings"][0]["replay_status"], "uncertainty")

    def test_replay_diff_never_emits_secret_values(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write(root, "app.py", 'API_KEY = "original-secret-value"\n')
            inspection = inspect_repository(request(root))
            finding = next(item for item in inspection["scan_report"]["findings"] if item["type"] == "hardcoded_secret")
            evaluation = {"findings": [{"id": finding["id"], "status": "valid", "closure": "Remove source secret.", "scope": {"include": ["app.py"], "exclude": []}, "success_criteria": ["No source secret signal remains."], "validator": "audisor scan . --json"}]}
            validation = validate_inspection(inspection, evaluation)
            write(root, "app.py", "value = 1\n")
            result = replay_inspection(inspection, validation)
        self.assertNotIn("original-secret-value", json.dumps(result))

    def test_replay_returns_bounded_visual_diff_for_scoped_image(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write(root, "app.py", "def broken(:\n")
            write_image(root, "screen.png", (0, 0, 0))
            inspection = inspect_repository(request(root))
            evaluation = valid_evaluation(inspection)
            evaluation["findings"][0]["scope"]["include"].append("screen.png")
            validation = validate_inspection(inspection, evaluation)
            write(root, "app.py", "def fixed():\n    return 1\n")
            write_image(root, "screen.png", (255, 255, 255))
            result = replay_inspection(inspection, validation)
        image_diff = next(item["image_diff"] for item in result["diff_view"] if item["path"] == "screen.png")
        self.assertEqual(image_diff["status"], "valid")
        self.assertGreater(image_diff["changed_pixel_count"], 0)
        self.assertEqual(image_diff["panels"], ["before", "after", "difference"])
        self.assertTrue(image_diff["diff_png_base64"])

    def test_replay_keeps_deleted_scoped_image_uncertain(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write(root, "app.py", "def broken(:\n")
            write_image(root, "screen.png", (0, 0, 0))
            inspection = inspect_repository(request(root))
            evaluation = valid_evaluation(inspection)
            evaluation["findings"][0]["scope"]["include"].append("screen.png")
            validation = validate_inspection(inspection, evaluation)
            write(root, "app.py", "def fixed():\n    return 1\n")
            (root / "screen.png").unlink()
            result = replay_inspection(inspection, validation)
        image_diff = next(item["image_diff"] for item in result["diff_view"] if item["path"] == "screen.png")
        self.assertEqual(image_diff, {"status": "uncertainty", "reason": "image_added_or_deleted"})

    def test_replay_summarizes_unrelated_image_without_exposing_visual_content(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write(root, "app.py", "def broken(:\n")
            write_image(root, "unrelated.png", (0, 0, 0))
            inspection = inspect_repository(request(root))
            validation = validate_inspection(inspection, valid_evaluation(inspection))
            write(root, "app.py", "def fixed():\n    return 1\n")
            write_image(root, "unrelated.png", (255, 255, 255))
            result = replay_inspection(inspection, validation)
        self.assertEqual([item for item in result["diff_view"] if item["path"] == "unrelated.png"], [])
        self.assertIn({"path": "unrelated.png", "status": "modified"}, result["unrelated_change_summary"])

    def test_image_limits_are_explicit_uncertainty(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_image(root, "screen.png", (0, 0, 0))
            with patch("audisor.artifacts._MAX_IMAGE_BYTES", 1):
                inspection = inspect_repository(request(root))
        image = next(item["image"] for item in inspection["source_snapshot"] if item["path"] == "screen.png")
        self.assertEqual(image, {"status": "uncertainty", "reason": "image_byte_limit"})

    def test_cli_artifact_smoke(self):
        with tempfile.TemporaryDirectory() as directory:
            artifacts = Path(directory)
            root = artifacts / "repo"
            write(root, "app.py", "def broken(:\n")
            request_path = artifacts / "request.json"
            request_path.write_text(json.dumps({"inspection_id": "cli-001", "repository_root": str(root), "issue": "Fix app.py"}), encoding="utf-8")
            inspect = subprocess.run([sys.executable, "-m", "audisor.cli", "inspect", str(request_path), "--json"], capture_output=True, text=True, check=True)
            inspection = json.loads(inspect.stdout)
            inspection_path = artifacts / "inspection.json"
            inspection_path.write_text(inspect.stdout, encoding="utf-8")
            evaluation_path = artifacts / "evaluation.json"
            evaluation_path.write_text(json.dumps(valid_evaluation(inspection)), encoding="utf-8")
            validate = subprocess.run([sys.executable, "-m", "audisor.cli", "validate", str(inspection_path), str(evaluation_path), "--json"], capture_output=True, text=True, check=True)
            validation_path = artifacts / "validation.json"
            validation_path.write_text(validate.stdout, encoding="utf-8")
            write(root, "app.py", "def fixed():\n    return 1\n")
            replay = subprocess.run([sys.executable, "-m", "audisor.cli", "replay", str(inspection_path), str(validation_path), "--json"], capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(replay.stdout)["overall_replay_status"], "resolved")

    def test_cli_json_is_safe_for_a_windows_legacy_codepage(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "repo"
            write(root, "app.py", "value = 1\n")
            request_path = Path(directory) / "request.json"
            request_path.write_text(json.dumps({"inspection_id": "unicode-001", "repository_root": str(root), "issue": "Fix caf\u00e9 output"}), encoding="utf-8")
            environment = dict(os.environ, PYTHONIOENCODING="cp1252")
            result = subprocess.run([sys.executable, "-m", "audisor.cli", "inspect", str(request_path), "--json"], capture_output=True, text=True, encoding="cp1252", env=environment, check=True)
        self.assertEqual(json.loads(result.stdout)["original_issue"], "Fix caf\u00e9 output")


if __name__ == "__main__":
    unittest.main()
