"""Portable evidence bundle generator for the Audisor re-check.

Read-only over the evidence. Produces:
  - evidence-inventory.json : every evidence file with sha256 + size
  - sanitization-report.json: portability scan reported by token CATEGORY
                              (never echoes raw host tokens)

The two generated files are excluded from the inventory (a manifest cannot hash
itself) but ARE re-scanned at the end to prove they introduce no leak.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

RECHECK = Path(__file__).resolve().parent
INVENTORY = RECHECK / "evidence-inventory.json"
SANITIZATION = RECHECK / "sanitization-report.json"
GENERATED = {INVENTORY.name, SANITIZATION.name}


def _token_categories() -> dict[str, str]:
    home = Path.home()
    repo = RECHECK.parents[2]  # repository root (derived, not hardcoded)
    categories: dict[str, str] = {}
    # Order matters: match longer/more specific tokens first.
    categories[str(repo).replace("\\", "/")] = "<REPO_ROOT>"
    categories[str(repo).replace("/", "\\")] = "<REPO_ROOT>"
    # JSON-escaped (double-backslash) form, as it appears inside captured stdout.
    categories[str(repo).replace("\\", "\\\\")] = "<REPO_ROOT>"
    categories[str(home).replace("\\", "/")] = "<HOME>"
    categories[str(home).replace("/", "\\")] = "<HOME>"
    # JSON-escaped (double-backslash) form, as it appears inside captured stdout.
    categories[str(home).replace("\\", "\\\\")] = "<HOME>"
    categories[home.name] = "<USER>"
    return categories


def _scan_text(text: str, categories: dict[str, str]) -> list[str]:
    hits: set[str] = set()
    for token, placeholder in categories.items():
        if token and token in text:
            hits.add(placeholder)
    return sorted(hits)


def main() -> int:
    categories = _token_categories()
    files = sorted(
        p
        for p in RECHECK.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts
    )

    # Inventory (exclude the generated manifest itself).
    entries = []
    for path in files:
        if path.name in GENERATED:
            continue
        data = path.read_bytes()
        entries.append(
            {
                "path": path.relative_to(RECHECK).as_posix(),
                "sha256": hashlib.sha256(data).hexdigest(),
                "size_bytes": len(data),
            }
        )

    # Portability scan over all non-generated files.
    leak_details = {}
    for path in files:
        if path.name in GENERATED:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = path.read_bytes().decode("utf-8", errors="replace")
        hits = _scan_text(text, categories)
        if hits:
            leak_details[path.relative_to(RECHECK).as_posix()] = hits

    # Classify: machine evidence (result JSONs + reports) must be portable;
    # proof scripts are reproducers and may carry host paths.
    evidence_files = [
        e["path"]
        for e in entries
        if e["path"].endswith("_result.json") or e["path"].endswith(".md")
    ]
    evidence_leaks = {p: leak_details[p] for p in evidence_files if p in leak_details}

    inventory = {
        "bundle": "audisor-backend-recheck",
        "file_count": len(entries),
        "entries": entries,
    }
    sanitization = {
        "token_categories_scanned": sorted(set(categories.values())),
        "evidence_files": evidence_files,
        "evidence_files_portable": not evidence_leaks,
        "evidence_leaks_by_category": evidence_leaks,
        "all_leaks_by_category": leak_details,
    }

    INVENTORY.write_text(json.dumps(inventory, ensure_ascii=True, indent=2, sort_keys=True), encoding="utf-8")
    SANITIZATION.write_text(json.dumps(sanitization, ensure_ascii=True, indent=2, sort_keys=True), encoding="utf-8")

    # Re-scan the two generated files to prove they introduce no raw token.
    generated_leaks = {}
    for path in (INVENTORY, SANITIZATION):
        hits = _scan_text(path.read_text(encoding="utf-8"), categories)
        if hits:
            generated_leaks[path.name] = hits

    checks = {
        "inventory_written": INVENTORY.is_file(),
        "sanitization_report_written": SANITIZATION.is_file(),
        "evidence_files_portable": bool(not evidence_leaks),
        "generated_files_leak_free": bool(not generated_leaks),
        "every_file_inventoried": (
            {e["path"] for e in entries} | GENERATED == {p.relative_to(RECHECK).as_posix() for p in files}
        ),
    }
    report = {"checks": checks, "all_checks_passed": all(checks.values()), "file_count": len(entries)}
    print(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True))
    return 0 if report["all_checks_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
