from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from audisor.artifacts import ArtifactError, verify_artifact
from audisor.contracts import InspectionRequest
from audisor.inspection import inspect_repository
from audisor.trace import trace_inspection


def write(root: Path, relative: str, content: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def inspect(root: Path) -> dict:
    return inspect_repository(
        InspectionRequest.from_mapping(
            {"inspection_id": "trace-001", "repository_root": str(root), "issue": "Fix app/service.py behavior."}
        )
    )


class TraceTests(unittest.TestCase):
    def test_trace_maps_parents_entrypoints_tests_and_dynamic_uncertainty(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write(root, "pyproject.toml", "[project]\nname = 'fixture'\nversion = '0'\n[project.scripts]\ndemo = 'app.main:main'\n")
            write(root, "app/__init__.py", "")
            write(root, "app/store.py", "def read():\n    return 1\n")
            write(root, "app/service.py", "import importlib\nfrom app.store import read\n\ndef process(name):\n    return importlib.import_module(name), read()\n")
            write(root, "app/main.py", "from app.service import process\n\ndef main():\n    return process('plugin')\n")
            write(root, "tests/test_service.py", "from app.service import process\n")
            trace = trace_inspection(inspect(root))
        verify_artifact(trace, "audisor.trace", "trace_sha256")
        service = next(item for item in trace["seed_details"] if item["file"] == "app/service.py")
        self.assertEqual(service["direct_dependencies"], ["app/store.py"])
        self.assertEqual(service["direct_parents"], ["app/main.py", "tests/test_service.py"])
        self.assertEqual(service["direct_test_importers"], ["tests/test_service.py"])
        self.assertEqual(service["reached_by_entrypoints"], ["demo"])
        self.assertEqual(trace["uncertainties"], [{"file": "app/service.py", "line": 5, "reason": "dynamic_import_target_not_static"}])

    def test_trace_blocks_changed_original_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write(root, "app.py", "value = 1\n")
            inspection = inspect(root)
            write(root, "app.py", "value = 2\n")
            with self.assertRaises(ArtifactError):
                trace_inspection(inspection)

    def test_cli_trace_smoke(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "repo"
            write(root, "app.py", "value = 1\n")
            inspection_path = Path(directory) / "inspection.json"
            inspection_path.write_text(json.dumps(inspect(root)), encoding="utf-8")
            result = subprocess.run([sys.executable, "-m", "audisor.cli", "trace", str(inspection_path), "--json"], capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout)["artifact_type"], "audisor.trace")


if __name__ == "__main__":
    unittest.main()
