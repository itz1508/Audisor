from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


REPOSITORY = Path(__file__).resolve().parents[2]


class ReleaseAssetsTests(unittest.TestCase):
    def test_release_metadata_and_plugin_are_consistent(self) -> None:
        pyproject = (REPOSITORY / "backend" / "pyproject.toml").read_text(encoding="utf-8")
        plugin = json.loads((REPOSITORY / "plugins" / "audisor" / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
        marketplace = json.loads((REPOSITORY / "marketplace.json").read_text(encoding="utf-8"))
        self.assertIn('version = "0.2.0"', pyproject)
        self.assertEqual(plugin["name"], "audisor")
        self.assertEqual(plugin["version"], "0.2.0")
        self.assertEqual(plugin["license"], "Apache-2.0")
        self.assertEqual(marketplace["plugins"][0]["source"]["path"], "./plugins/audisor")
        self.assertIn("audisor install-codex", (REPOSITORY / "scripts" / "install.ps1").read_text(encoding="utf-8"))
        self.assertIn("audisor install-codex", (REPOSITORY / "scripts" / "install.sh").read_text(encoding="utf-8"))

    def test_demo_produces_safe_replay_evidence_without_mutating_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output"
            result = subprocess.run(
                [sys.executable, str(REPOSITORY / "scripts" / "run_demo.py"), "--output-root", str(output)],
                capture_output=True,
                text=True,
                check=True,
            )
            summary = json.loads(result.stdout)
            replay = json.loads((output / "replay.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["status"], "completed")
        self.assertTrue(summary["fixture_unchanged"])
        self.assertEqual(replay["overall_replay_status"], "resolved")
        self.assertTrue(any(item["path"] == "screen.png" and item["image_diff"]["status"] == "valid" for item in replay["diff_view"]))


if __name__ == "__main__":
    unittest.main()
