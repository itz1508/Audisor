from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator


REPOSITORY = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPOSITORY / "backend" / "src" / "audisor" / "schemas" / "v1" / "llm-statement.schema.json"


def statement() -> dict:
    evidence = {"kind": "scan_finding", "reference": "syntax_error:app.py:example"}
    return {
        "schema_version": "1.0.0",
        "statement_id": "demo-statement-001",
        "producer": {"kind": "codex", "label": "Codex"},
        "inspection_ref": {"inspection_id": "demo-inspection-001", "manifest_sha256": "a" * 64},
        "finding_ids": ["syntax_error:app.py:example"],
        "behavior": {
            "expected": {"description": "The module parses.", "evidence_refs": [{"kind": "requirement", "reference": "Python grammar"}]},
            "actual": {"description": "The parser reports a syntax error.", "evidence_refs": [evidence]},
        },
        "call_path": {"status": "valid", "entrypoint": "app.py:main:1", "hops": ["app.py:main:1"]},
        "constraints": {"explicit_constraints": ["Keep the repair scoped to app.py."], "prohibited_changes": ["Do not change public behavior."]},
        "diagnosis": {
            "hypotheses": [{"rank": 1, "claim": "The function declaration is malformed.", "confidence": "confirmed", "evidence_refs": [evidence]}],
            "reasoned_diagnosis": "The parser evidence confirms the declaration cannot be imported.",
            "evidence_refs": [evidence],
        },
        "repair_success_criteria": [{"check": "python -m py_compile app.py", "expected_result": "Exit code 0."}],
        "one_shot": {"viable": True, "blocker": None},
    }


class LlmStatementSchemaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(self.schema)
        self.validator = Draft202012Validator(self.schema)

    def errors(self, value: dict) -> list[str]:
        return [error.message for error in self.validator.iter_errors(value)]

    def test_accepts_one_shot_statement_with_evidence_references(self) -> None:
        self.assertEqual(self.errors(statement()), [])

    def test_rejects_snapshot_and_replay_fields(self) -> None:
        value = statement()
        value["source_snapshot"] = []
        value["replay"] = {"result_sha256": "not-allowed"}
        self.assertTrue(self.errors(value))

    def test_rejects_viable_statement_with_a_blocker(self) -> None:
        value = statement()
        value["one_shot"] = {"viable": True, "blocker": "Missing production log."}
        self.assertTrue(self.errors(value))

    def test_requires_honest_call_path_uncertainty(self) -> None:
        value = deepcopy(statement())
        value["call_path"] = {"status": "uncertainty"}
        self.assertTrue(self.errors(value))


if __name__ == "__main__":
    unittest.main()
