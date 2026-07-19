from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping


_ANALYSIS_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_INSPECTION_KEYS = frozenset({"inspection_id", "repository_root", "issue", "baseline"})


class ContractError(ValueError):
    pass


@dataclass(frozen=True)
class InspectionRequest:
    inspection_id: str
    repository_root: str
    issue: str
    baseline: str | None = None

    @classmethod
    def from_mapping(cls, value: object) -> "InspectionRequest":
        if not isinstance(value, Mapping) or set(value) - _INSPECTION_KEYS:
            raise ContractError("inspection request must contain only inspection_id, repository_root, issue, and optional baseline")
        inspection_id = value.get("inspection_id")
        repository_root = value.get("repository_root")
        issue = value.get("issue")
        baseline = value.get("baseline")
        if not isinstance(inspection_id, str) or not _ANALYSIS_ID.fullmatch(inspection_id):
            raise ContractError("inspection_id must be 1-64 letters, digits, dots, underscores, or hyphens")
        if not isinstance(repository_root, str) or not repository_root.strip():
            raise ContractError("repository_root must be a non-empty path")
        if not isinstance(issue, str) or not issue.strip() or len(issue) > 20_000:
            raise ContractError("issue must be non-empty and at most 20000 characters")
        if baseline is not None and (not isinstance(baseline, str) or not baseline.strip()):
            raise ContractError("baseline must be a non-empty Git ref when supplied")
        return cls(inspection_id=inspection_id, repository_root=repository_root, issue=issue, baseline=baseline)

