from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from audisor.finding_registry import FINDING_REGISTRY
from audisor.gap_contract import GapEvaluationError, validate_gap_evaluation
from audisor.scanner import scan_report


def write(root: Path, relative: str, content: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def types(report) -> set[str]:
    return {item["type"] for item in report.findings}


class ScanTests(unittest.TestCase):
    def test_structural_and_secret_findings_are_safe(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write(root, "bad.py", "def broken(:\n")
            write(root, "bad.json", "{")
            write(root, "bad.toml", "[project\n")
            write(root, "bad.yaml", "key: [\n")
            write(root, "secret.py", 'API_KEY = "super-secret-value"\n')
            report = scan_report(root)
        self.assertTrue({"syntax_error", "invalid_json", "invalid_toml", "invalid_yaml", "hardcoded_secret"}.issubset(types(report)))
        self.assertNotIn("super-secret-value", json.dumps(report.as_dict()))

    def test_read_error_links_dependencies_entrypoints_and_duplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write(root, "locked.py", "value = 1\n")
            write(root, "pkg/__init__.py", "")
            write(root, "pkg/app.py", "from pkg.missing import value\nimport requests\n\ndef main():\n    return 1\n")
            write(root, "schema.json", '{"$ref": "missing.json"}')
            write(root, "a.py", "def shared():\n    return 1\n")
            write(root, "b.py", "def shared():\n    return 1\n")
            write(root, "pyproject.toml", "[project]\nname = 'fixture'\nversion = '0'\n[project.scripts]\nvalid = 'pkg.app:main'\nbroken = 'pkg.nope:main'\n")
            original = Path.read_text

            def unreadable(path, *args, **kwargs):
                if path.name == "locked.py":
                    raise OSError("locked")
                return original(path, *args, **kwargs)

            with patch.object(Path, "read_text", unreadable):
                report = scan_report(root)
        self.assertTrue({"read_error", "missing_local_import", "missing_schema_reference", "dependency_declaration_mismatch", "invalid_script_entrypoint", "missing_validation_registration", "duplicate_implementation", "overlapping_symbol"}.issubset(types(report)))

    def test_standard_and_relative_imports_are_not_dependencies(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write(root, "pkg/__init__.py", "from .app import value\n")
            write(root, "pkg/app.py", "from __future__ import annotations\nvalue = 1\n")
            report = scan_report(root)
        self.assertNotIn("dependency_declaration_mismatch", types(report))

    def test_nested_requirements_local_packages_jsonc_and_reexported_entrypoint(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write(root, ".vscode/settings.json", '{\n  // VS Code accepts JSONC here\n  "editor.tabSize": 2\n}\n')
            write(root, "dashboard/requirements.txt", "PySide6>=6\n")
            write(root, "dashboard/ui/__init__.py", "")
            write(root, "dashboard/ui/widgets.py", "class Panel: pass\n")
            write(root, "dashboard/app.py", "import PySide6\nfrom ui.widgets import Panel\n")
            write(root, "pyproject.toml", "[project]\nname = 'fixture'\nversion = '0'\n[project.scripts]\nfixture = 'pkg.__main__:main'\n")
            write(root, "pkg/__init__.py", "")
            write(root, "pkg/cli.py", "def main():\n    return 1\n")
            write(root, "pkg/__main__.py", "from pkg.cli import main\n")
            report = scan_report(root)
        self.assertNotIn("invalid_json", types(report))
        self.assertNotIn("dependency_declaration_mismatch", {item["type"] for item in report.findings if item["file"] == "dashboard/app.py"})
        self.assertNotIn("missing_local_import", {item["type"] for item in report.findings if item["file"] == "dashboard/app.py"})
        self.assertNotIn("invalid_script_entrypoint", types(report))

    def test_drift_and_registry_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write(root, "app.py", "value = 1\n")
            subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.email", "tests@example.invalid"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.name", "Audisor Tests"], cwd=root, check=True)
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(["git", "commit", "-m", "baseline"], cwd=root, check=True, capture_output=True)
            write(root, "app.py", "value = 2\n")
            report = scan_report(root, baseline="HEAD")
        self.assertIn("repository_drift", types(report))
        self.assertEqual(report.baseline["status"], "valid")
        self.assertTrue(all(item.required_evidence and item.validator for item in FINDING_REGISTRY.values()))

    def test_drift_excludes_generated_content_and_aggregates_large_change_sets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write(root, "app.py", "value = 1\n")
            subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.email", "tests@example.invalid"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.name", "Audisor Tests"], cwd=root, check=True)
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(["git", "commit", "-m", "baseline"], cwd=root, check=True, capture_output=True)
            write(root, "app.py", "value = 2\n")
            write(root, "new.py", "value = 3\n")
            write(root, "node_modules/generated.py", "value = 4\n")
            report = scan_report(root, baseline="HEAD")
        drift = [item for item in report.findings if item["type"] == "repository_drift"]
        self.assertEqual(len(drift), 1)
        self.assertEqual(drift[0]["file"], ".")
        self.assertEqual(drift[0]["evidence"]["changed_path_count"], 2)
        self.assertEqual(report.baseline["eligible_changed_path_count"], 2)

    def test_gap_contract_requires_all_finding_ids_and_valid_closure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write(root, "bad.py", "def broken(:\n")
            report = scan_report(root)
        valid = {"findings": [{"id": report.findings[0]["id"], "status": "valid", "closure": "Correct syntax.", "scope": {"include": ["bad.py"], "exclude": []}, "success_criteria": ["Python parses bad.py."], "validator": "python -m py_compile bad.py"}]}
        validate_gap_evaluation(report, valid)
        with self.assertRaises(GapEvaluationError):
            validate_gap_evaluation(report, {"findings": []})

    def test_cli_exposes_only_canonical_commands_and_scan_is_json(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write(root, "app.py", "value = 1\n")
            result = subprocess.run([sys.executable, "-m", "audisor.cli", "scan", str(root), "--json"], capture_output=True, text=True, check=True)
            help_result = subprocess.run([sys.executable, "-m", "audisor.cli", "--help"], capture_output=True, text=True, check=True)
        self.assertIn("schema_version", json.loads(result.stdout))
        self.assertNotIn("normalize", help_result.stdout)


if __name__ == "__main__":
    unittest.main()
