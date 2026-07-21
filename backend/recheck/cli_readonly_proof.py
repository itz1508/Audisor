"""CLI battery + read-only proof for the standalone Audisor tool.

Read-only. Exercises every evidence command in the documented order
(scan -> inspect -> trace -> normalize -> validate -> replay) through the
public CLI entrypoint, using artifact files stored OUTSIDE the inspected
repository. Hashes the repository tree before and after to prove the tool
never mutates the repository it inspects.

Emits a single JSON object to stdout.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

CLI = [sys.executable, "-m", "audisor.cli"]


def _run(*args: str, expect_zero: bool = True) -> tuple[int, str]:
    proc = subprocess.run([*CLI, *args], capture_output=True, text=True)
    if expect_zero and proc.returncode != 0:
        raise SystemExit(f"command failed ({proc.returncode}): {args}\n{proc.stderr}")
    return proc.returncode, proc.stdout


def _tree_manifest(root: Path) -> dict[str, str]:
    manifest: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            manifest[str(path.relative_to(root)).replace("\\", "/")] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
    return manifest


def main() -> int:
    checks: dict[str, object] = {}
    with tempfile.TemporaryDirectory() as directory:
        workspace = Path(directory)
        artifacts = workspace / "artifacts"
        artifacts.mkdir()
        repo = workspace / "repo"
        repo.mkdir()
        (repo / "app.py").write_text("def broken(:\n", encoding="utf-8")

        before = _tree_manifest(repo)

        # scan
        rc, out = _run("scan", str(repo), "--json")
        scan = json.loads(out)
        checks["scan_ok"] = rc == 0 and "findings" in scan

        # inspect -> inspection.json (outside the repo)
        request_path = artifacts / "request.json"
        request_path.write_text(
            json.dumps({"inspection_id": "recheck-001", "repository_root": str(repo), "issue": "Fix app.py"}),
            encoding="utf-8",
        )
        rc, out = _run("inspect", str(request_path), "--json")
        inspection = json.loads(out)
        inspection_path = artifacts / "inspection.json"
        inspection_path.write_text(out, encoding="utf-8")
        checks["inspect_ok"] = rc == 0 and inspection.get("artifact_type") == "audisor.inspection"

        syntax_finding = next(
            item for item in inspection["scan_report"]["findings"] if item["type"] == "syntax_error"
        )

        # trace
        rc, out = _run("trace", str(inspection_path), "--json")
        trace = json.loads(out)
        checks["trace_ok"] = rc == 0 and trace.get("artifact_type") == "audisor.trace"

        # normalize (needs an LLM statement referencing real evidence)
        statement = {
            "schema_version": "1.0.0",
            "statement_id": "recheck-normalize-001",
            "producer": {"kind": "codex", "label": "Codex"},
            "inspection_ref": {
                "inspection_id": inspection["inspection_id"],
                "manifest_sha256": inspection["manifest_sha256"],
            },
            "finding_ids": [syntax_finding["id"]],
            "diagnosis": {
                "hypotheses": [
                    {
                        "rank": 1,
                        "claim": "app.py has a syntax error.",
                        "confidence": "likely",
                        "evidence_refs": [{"kind": "scan_finding", "reference": syntax_finding["id"]}],
                    }
                ],
                "reasoned_diagnosis": "The scanner reported a syntax error in app.py.",
                "evidence_refs": [{"kind": "scan_finding", "reference": syntax_finding["id"]}],
            },
            "constraints": {"explicit_constraints": ["Keep the change minimal."], "prohibited_changes": []},
            "repair_success_criteria": [{"check": "python -m py_compile app.py", "expected_result": "Parses cleanly."}],
            "one_shot": {"viable": True, "blocker": None},
        }
        statement_path = artifacts / "llm-statement.json"
        statement_path.write_text(json.dumps(statement), encoding="utf-8")
        rc, out = _run("normalize", str(inspection_path), str(statement_path), "--json")
        normalization = json.loads(out)
        checks["normalize_ok"] = (
            rc == 0
            and normalization.get("artifact_type") == "audisor.normalization_package"
            and "source_snapshot" not in normalization
        )

        # validate -> validation.json
        evaluation = {
            "findings": [
                {
                    "id": syntax_finding["id"],
                    "status": "valid",
                    "closure": "Correct the syntax error.",
                    "scope": {"include": ["app.py"], "exclude": []},
                    "success_criteria": ["Python parses app.py."],
                    "validator": "python -m py_compile app.py",
                }
                if item["id"] == syntax_finding["id"]
                else {"id": item["id"], "status": "not_valid"}
                for item in inspection["scan_report"]["findings"]
            ]
        }
        evaluation_path = artifacts / "evaluation.json"
        evaluation_path.write_text(json.dumps(evaluation), encoding="utf-8")
        rc, out = _run("validate", str(inspection_path), str(evaluation_path), "--json")
        validation = json.loads(out)
        validation_path = artifacts / "validation.json"
        validation_path.write_text(out, encoding="utf-8")
        checks["validate_ok"] = rc == 0 and validation.get("artifact_type") == "audisor.validation"

        # Read-only proof #1: scan+inspect+trace+normalize+validate left the
        # repository tree byte-identical to its pre-tool state.
        after_readonly_tools = _tree_manifest(repo)
        checks["repo_unchanged_by_readonly_tools"] = before == after_readonly_tools

        # Codex would repair here; simulate the approved repair inside the scope.
        (repo / "app.py").write_text("def fixed():\n    return 1\n", encoding="utf-8")
        after_repair = _tree_manifest(repo)

        # replay
        rc, out = _run("replay", str(inspection_path), str(validation_path), "--json")
        replay = json.loads(out)
        checks["replay_ok"] = (
            rc == 0
            and replay.get("artifact_type") == "audisor.replay_result"
            and replay.get("overall_replay_status") == "resolved"
        )

        after = _tree_manifest(repo)

        # Read-only proof #2: replay did not mutate the repo; the only change is
        # our own simulated repair.
        checks["only_our_repair_changed_repo"] = (
            set(before) == set(after)
            and after == after_repair
            and before["app.py"] != after["app.py"]
        )
        # Artifacts were written outside the repo, never inside it.
        checks["artifacts_outside_repo"] = all(
            not str(p).startswith(str(repo)) for p in artifacts.rglob("*")
        )

    report = {"checks": checks, "all_checks_passed": all(bool(v) for v in checks.values())}
    print(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True))
    return 0 if report["all_checks_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
