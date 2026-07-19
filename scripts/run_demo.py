from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil

from PIL import Image

from audisor.contracts import InspectionRequest
from audisor.inspection import inspect_repository
from audisor.replay import replay_inspection
from audisor.trace import trace_inspection
from audisor.validation import validate_inspection


def _sha256_tree(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run(output_root: Path) -> dict[str, object]:
    repository_root = Path(__file__).resolve().parents[1]
    fixture = repository_root / "demo" / "fixture"
    output_root = output_root.resolve()
    workspace = output_root / "working-copy"
    if workspace.exists():
        raise FileExistsError(f"Refusing to overwrite existing demo output: {workspace}")
    output_root.mkdir(parents=True, exist_ok=True)

    fixture_before = _sha256_tree(fixture)
    shutil.copytree(fixture, workspace)
    Image.new("RGB", (16, 16), (0, 0, 0)).save(workspace / "screen.png", format="PNG")

    inspection = inspect_repository(
        InspectionRequest.from_mapping(
            {
                "inspection_id": "audisor-public-demo-v1",
                "repository_root": str(workspace),
                "issue": "Remove the key-shaped source assignment in app/service.py and refresh screen.png.",
            }
        )
    )
    trace = trace_inspection(inspection)
    evaluation = {"findings": []}
    for finding in inspection["scan_report"]["findings"]:
        if finding["type"] == "hardcoded_secret":
            evaluation["findings"].append(
                {
                    "id": finding["id"],
                    "status": "valid",
                    "closure": "Remove the key-shaped source assignment.",
                    "scope": {"include": ["app/service.py", "screen.png"], "exclude": []},
                    "success_criteria": ["The scanner no longer reports a hardcoded_secret finding for app/service.py."],
                    "validator": "audisor scan <working-copy> --json",
                }
            )
        else:
            evaluation["findings"].append({"id": finding["id"], "status": "not_valid"})
    validation = validate_inspection(inspection, evaluation)

    (workspace / "app" / "service.py").write_text("def process(value: str) -> str:\n    return value.strip()\n", encoding="utf-8")
    Image.new("RGB", (16, 16), (255, 255, 255)).save(workspace / "screen.png", format="PNG")
    replay = replay_inspection(inspection, validation)

    hardcoded = [item for item in replay["findings"] if item["original_status"] == "valid"]
    if len(hardcoded) != 1 or hardcoded[0]["replay_status"] != "resolved":
        raise RuntimeError("demo_replay_not_resolved")
    if not any(item["path"] == "screen.png" and item.get("image_diff", {}).get("status") == "valid" for item in replay["diff_view"]):
        raise RuntimeError("demo_image_diff_missing")
    fixture_after = _sha256_tree(fixture)
    if fixture_before != fixture_after:
        raise RuntimeError("demo_fixture_changed")

    for name, artifact in (("inspection", inspection), ("trace", trace), ("validation", validation), ("replay", replay)):
        _write_json(output_root / f"{name}.json", artifact)
    summary = {
        "status": "completed",
        "fixture_unchanged": True,
        "trace_entrypoints": [item["script"] for item in trace["entrypoints"]],
        "resolved_finding_ids": [item["id"] for item in hardcoded],
        "output_root": str(output_root),
    }
    _write_json(output_root / "summary.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the safe Audisor public-release fixture.")
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.output_root), ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
