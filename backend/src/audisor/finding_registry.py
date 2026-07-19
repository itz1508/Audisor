from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FindingDefinition:
    required_evidence: tuple[str, ...]
    false_positive_rule: str
    closure_guidance: str
    validator: str
    human_decision_required: bool = False


FINDING_REGISTRY: dict[str, FindingDefinition] = {
    "read_error": FindingDefinition(("file", "reason"), "The scanner could not read the file; it is not a source defect claim.", "Restore readable source or exclude the unsupported artifact.", "Read the target file with the configured encoding."),
    "syntax_error": FindingDefinition(("file", "line", "message"), "Only Python parser errors qualify.", "Correct the bounded syntax defect.", "Parse the file with Python."),
    "invalid_json": FindingDefinition(("file", "line", "message"), "Only JSON decoder errors qualify.", "Correct the malformed JSON.", "Parse the file as JSON."),
    "invalid_toml": FindingDefinition(("file", "message"), "Only TOML decoder errors qualify.", "Correct the malformed TOML.", "Parse the file as TOML."),
    "invalid_yaml": FindingDefinition(("file", "message"), "Only YAML parser errors qualify.", "Correct the malformed YAML.", "Parse the file with safe YAML loading."),
    "missing_local_import": FindingDefinition(("file", "line", "module"), "External modules and ambiguous relative imports are excluded.", "Correct the local module reference or restore its source file.", "Parse imports and resolve the local module path."),
    "missing_schema_reference": FindingDefinition(("file", "reference"), "Only local $ref paths are checked; URLs and anchors are excluded.", "Correct the reference or add the referenced schema.", "Resolve the referenced local path."),
    "invalid_script_entrypoint": FindingDefinition(("file", "script", "target"), "Only declared Python project scripts are checked; one imported or re-exported target is resolved before reporting.", "Correct the declared target or restore the module.", "Resolve the module portion of the script target."),
    "dependency_declaration_mismatch": FindingDefinition(("file", "line", "module"), "Standard-library and local modules are excluded, and a finding requires the nearest in-target dependency manifest.", "Declare the dependency or remove the unsupported import.", "Compare imported third-party module names with project dependencies."),
    "hardcoded_secret": FindingDefinition(("file", "line", "field"), "A key-shaped assignment is a signal, not proof that the value is live.", "Move the value out of source and rotate it when the user confirms it is real.", "Re-scan for the signal without exposing the value.", True),
    "duplicate_implementation": FindingDefinition(("file", "duplicate_files"), "Identical normalized text can be intentional fixtures or compatibility code.", "Consolidate only after active callers prove duplicate ownership.", "Compare active callers and run focused behavior tests.", True),
    "overlapping_symbol": FindingDefinition(("file", "symbol", "overlapping_files"), "Same top-level names can belong to separate modules intentionally.", "Align ownership only after active callers prove an overlap defect.", "Trace imports and callers for each symbol.", True),
    "repository_drift": FindingDefinition(("file", "status", "baseline"), "A Git difference is evidence of change, not proof of a defect.", "Confirm whether the changed path is in approved scope.", "Compare against the declared Git baseline.", True),
    "missing_validation_registration": FindingDefinition(("file", "script", "target"), "Only valid declared script entrypoints without a matching test reference qualify.", "Register or add a focused test for the active entrypoint.", "Run the registered focused validator."),
}


def finding_definition(finding_type: str) -> FindingDefinition:
    try:
        return FINDING_REGISTRY[finding_type]
    except KeyError as exc:
        raise ValueError(f"unknown finding type: {finding_type}") from exc
