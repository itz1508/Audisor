from __future__ import annotations

import ast
from collections import Counter
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tomllib
from typing import Any, Iterable

import yaml

from .finding_registry import FINDING_REGISTRY, finding_definition


_EXCLUDED = {".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache", "dist", "build", "snapshot"}
_EXTENSIONS = {".py", ".json", ".toml", ".yaml", ".yml"}
_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
_SECRET = re.compile(r"(?i)(?P<field>api[_-]?key|secret|token|password)\s*[:=]\s*['\"][^'\"]+['\"]")
_PATH = re.compile(r"(?<!\w)(?:[\w.-]+/)*[\w.-]+\.(?:py|json|toml|ya?ml)(?!\w)")
_DEPENDENCY = re.compile(r"^[A-Za-z0-9_.-]+")
_IMPORT_ALIASES = {"yaml": "pyyaml"}


@dataclass(frozen=True)
class ScanReport:
    schema_version: str
    repository_root: str
    baseline: dict[str, Any]
    findings: list[dict[str, Any]]
    summary: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProjectContext:
    root: Path
    declared_dependencies: frozenset[str]
    scripts: tuple[tuple[str, str], ...]
    project_file: str | None


def _is_excluded(relative: Path) -> bool:
    return any(part in _EXCLUDED for part in relative.parts)


def _is_jsonc(relative: Path) -> bool:
    return ".vscode" in relative.parts


def _is_requirement_file(path: Path) -> bool:
    return path.name == "requirements.txt" or (path.name.startswith("requirements.") and path.suffix == ".txt")


def _is_evidence_path(relative: Path) -> bool:
    return relative.suffix.lower() in _EXTENSIONS or relative.name == "pyproject.toml" or _is_requirement_file(relative)


def supported_paths(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if path.is_file() and path.suffix.lower() in _EXTENSIONS and not _is_excluded(relative):
            yield path


def evidence_paths(root: Path) -> Iterable[Path]:
    """Return source plus dependency manifests whose hashes qualify inspection evidence."""
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if path.is_file() and _is_evidence_path(relative) and not _is_excluded(relative):
            yield path


def image_paths(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if path.is_file() and path.suffix.lower() in _IMAGE_EXTENSIONS and not _is_excluded(relative):
            yield path


def _finding(finding_type: str, file: str, evidence: dict[str, Any]) -> dict[str, Any]:
    finding_definition(finding_type)
    fingerprint = hashlib.sha256(json.dumps(evidence, sort_keys=True, ensure_ascii=True).encode("utf-8")).hexdigest()[:12]
    return {"id": f"{finding_type}:{file}:{fingerprint}", "type": finding_type, "file": file, "evidence": evidence}


def _module_names(root: Path, relative: str, project_root: Path) -> set[str]:
    parts = (root / relative).relative_to(project_root).with_suffix("").parts
    if parts and parts[0] == "src":
        parts = parts[1:]
    if not parts:
        return set()
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return {".".join(parts)} if parts else set()


def _is_local_module(module: str, known_modules: set[str], local_prefixes: set[str]) -> bool:
    return module in known_modules or module.split(".", 1)[0] in local_prefixes


def _local_import_findings(
    parsed_python: list[tuple[str, ast.Module]],
    contexts_by_file: dict[str, ProjectContext | None],
    known_modules_by_context: dict[ProjectContext, set[str]],
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for relative, tree in parsed_python:
        context = contexts_by_file.get(relative)
        if context is None:
            continue
        known_modules = known_modules_by_context[context]
        local_prefixes = {module.split(".", 1)[0] for module in known_modules}
        for node in ast.walk(tree):
            module = node.module if isinstance(node, ast.ImportFrom) else None
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if _is_local_module(alias.name, known_modules, local_prefixes) and alias.name not in known_modules:
                        findings.append(_finding("missing_local_import", relative, {"line": node.lineno, "module": alias.name}))
            elif isinstance(node, ast.ImportFrom) and module and _is_local_module(module, known_modules, local_prefixes) and module not in known_modules:
                findings.append(_finding("missing_local_import", relative, {"line": node.lineno, "module": module}))
    return findings


def _dependency_findings(
    parsed_python: list[tuple[str, ast.Module]],
    contexts_by_file: dict[str, ProjectContext | None],
    known_modules_by_context: dict[ProjectContext, set[str]],
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    standard = set(sys.stdlib_module_names) | {"__future__"}
    seen: set[tuple[str, int, str]] = set()
    for relative, tree in parsed_python:
        context = contexts_by_file.get(relative)
        if context is None:
            continue
        known_modules = known_modules_by_context[context]
        local_prefixes = {module.split(".", 1)[0] for module in known_modules}
        declared = context.declared_dependencies
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.level:
                continue
            modules = [alias.name for alias in node.names] if isinstance(node, ast.Import) else [node.module] if isinstance(node, ast.ImportFrom) and node.module else []
            for module in modules:
                top = module.split(".", 1)[0]
                normalized = _IMPORT_ALIASES.get(top, top).replace("_", "-").lower()
                key = (relative, node.lineno, top)
                if key in seen or top in standard or _is_local_module(module, known_modules, local_prefixes) or normalized in declared:
                    continue
                seen.add(key)
                findings.append(_finding("dependency_declaration_mismatch", relative, {"line": node.lineno, "module": top}))
    return findings


def _walk_references(value: Any) -> Iterable[str]:
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "$ref" and isinstance(child, str):
                yield child
            yield from _walk_references(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_references(child)


def _schema_reference_findings(root: Path, documents: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for relative, document in documents.items():
        for reference in _walk_references(document):
            target = reference.split("#", 1)[0]
            if not target or "://" in target:
                continue
            candidate = (root / relative).parent / target
            if not candidate.is_file():
                findings.append(_finding("missing_schema_reference", relative, {"reference": reference}))
    return findings


def _declared_dependencies(values: Iterable[str]) -> set[str]:
    dependencies: set[str] = set()
    for value in values:
        if isinstance(value, str) and (match := _DEPENDENCY.match(value)):
            dependencies.add(match.group(0).replace("_", "-").lower())
    return dependencies


def _requirements_dependencies(path: Path) -> set[str]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return set()
    return _declared_dependencies(line.split("#", 1)[0].strip() for line in lines if not line.lstrip().startswith(("#", "-")))


def _project_contexts(root: Path, documents: dict[str, Any]) -> list[ProjectContext]:
    details: dict[Path, dict[str, Any]] = {}
    for relative, document in documents.items():
        if Path(relative).name != "pyproject.toml" or not isinstance(document, dict):
            continue
        project_root = (root / relative).parent
        project = document.get("project", {})
        project = project if isinstance(project, dict) else {}
        scripts_value = project.get("scripts", {})
        scripts = tuple((name, target) for name, target in scripts_value.items() if isinstance(name, str) and isinstance(target, str)) if isinstance(scripts_value, dict) else ()
        details[project_root] = {
            "dependencies": _declared_dependencies(project.get("dependencies", []) if isinstance(project.get("dependencies", []), list) else []),
            "scripts": scripts,
            "project_file": relative,
        }
    for path in root.rglob("requirements*.txt"):
        relative = path.relative_to(root)
        if not path.is_file() or _is_excluded(relative) or not _is_requirement_file(path):
            continue
        entry = details.setdefault(path.parent, {"dependencies": set(), "scripts": (), "project_file": None})
        entry["dependencies"].update(_requirements_dependencies(path))
    return [
        ProjectContext(project_root, frozenset(entry["dependencies"]), entry["scripts"], entry["project_file"])
        for project_root, entry in sorted(details.items(), key=lambda item: (len(item[0].relative_to(root).parts), str(item[0])), reverse=True)
    ]


def _context_for_path(root: Path, relative: str, contexts: list[ProjectContext]) -> ProjectContext | None:
    path = root / relative
    return next((context for context in contexts if path.is_relative_to(context.root)), None)


def _resolve_module(root: Path, project_root: Path, module: str) -> str | None:
    relative = Path(*module.split("."))
    for base in (project_root, project_root / "src"):
        for candidate in (base / relative.with_suffix(".py"), base / relative / "__init__.py"):
            if candidate.is_file():
                return candidate.relative_to(root).as_posix()
    return None


def _has_entrypoint_attribute(root: Path, project_root: Path, relative: str, target: str, remaining_import_hops: int = 1) -> bool:
    _, separator, attribute = target.partition(":")
    if not separator or not attribute:
        return False
    try:
        tree = ast.parse((root / relative).read_text(encoding="utf-8"), filename=relative)
    except (OSError, UnicodeDecodeError, SyntaxError):
        return False
    expected = attribute.split(".", 1)[0]
    for node in tree.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == expected:
            return True
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == expected for target in node.targets):
            return True
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == expected:
            return True
        if remaining_import_hops and isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                if (alias.asname or alias.name) != expected:
                    continue
                imported_relative = _resolve_module(root, project_root, node.module)
                if imported_relative and _has_entrypoint_attribute(root, project_root, imported_relative, f"{node.module}:{alias.name}", remaining_import_hops - 1):
                    return True
    return False


def _entrypoint_findings(root: Path, contexts: list[ProjectContext], contents: dict[str, str]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for context in contexts:
        if not context.project_file:
            continue
        project_relative = context.root.relative_to(root).as_posix()
        test_prefix = "tests/" if project_relative == "." else f"{project_relative}/tests/"
        test_contents = "\n".join(text for relative, text in contents.items() if relative.startswith(test_prefix))
        for script, target in context.scripts:
            module = target.split(":", 1)[0]
            resolved = _resolve_module(root, context.root, module)
            evidence = {"script": script, "target": target}
            if not resolved or not _has_entrypoint_attribute(root, context.root, resolved, target):
                findings.append(_finding("invalid_script_entrypoint", context.project_file, evidence))
            elif module not in test_contents:
                findings.append(_finding("missing_validation_registration", resolved, evidence))
    return findings


def _baseline(root: Path, requested: str | None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not requested:
        return {"requested": None, "status": "uncertainty", "detail": "baseline_not_supplied"}, []
    resolve = subprocess.run(["git", "-C", str(root), "rev-parse", "--verify", f"{requested}^{{commit}}"], capture_output=True, text=True)
    if resolve.returncode != 0:
        return {"requested": requested, "status": "uncertainty", "detail": "baseline_unavailable"}, []
    diff = subprocess.run(["git", "-C", str(root), "diff", "--name-status", requested, "--"], capture_output=True, text=True)
    untracked = subprocess.run(["git", "-C", str(root), "ls-files", "--others", "--exclude-standard"], capture_output=True, text=True)
    if diff.returncode != 0 or untracked.returncode != 0:
        return {"requested": requested, "status": "uncertainty", "detail": "baseline_compare_failed"}, []
    baseline = {"requested": requested, "resolved": resolve.stdout.strip(), "status": "valid"}
    findings: list[dict[str, Any]] = []
    changed: list[tuple[str, str]] = []
    for line in diff.stdout.splitlines():
        columns = line.split("\t")
        if len(columns) >= 2 and _is_evidence_path(Path(columns[-1])) and not _is_excluded(Path(columns[-1])):
            changed.append((columns[-1], columns[0]))
    for relative in untracked.stdout.splitlines():
        path = Path(relative)
        if relative and _is_evidence_path(path) and not _is_excluded(path):
            changed.append((relative, "untracked"))
    baseline["eligible_changed_path_count"] = len(changed)
    if len(changed) == 1:
        relative, status = changed[0]
        findings.append(_finding("repository_drift", relative, {"status": status, "baseline": requested}))
    elif changed:
        digest = hashlib.sha256(json.dumps(sorted(changed), ensure_ascii=True).encode("utf-8")).hexdigest()[:12]
        baseline["eligible_changed_path_digest"] = digest
        findings.append(_finding("repository_drift", ".", {"status": "aggregate", "baseline": requested, "changed_path_count": len(changed), "changed_path_digest": digest}))
    return baseline, findings


def scan_report(root: Path, baseline: str | None = None) -> ScanReport:
    root = root.expanduser().resolve()
    findings: list[dict[str, Any]] = []
    contents: dict[str, str] = {}
    documents: dict[str, Any] = {}
    parsed_python: list[tuple[str, ast.Module]] = []
    symbols: dict[str, list[str]] = {}
    for path in supported_paths(root):
        relative = path.relative_to(root).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            findings.append(_finding("read_error", relative, {"reason": type(exc).__name__}))
            continue
        contents[relative] = text
        if path.suffix == ".py":
            try:
                tree = ast.parse(text, filename=relative)
                parsed_python.append((relative, tree))
                for node in tree.body:
                    if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                        symbols.setdefault(node.name, []).append(relative)
            except SyntaxError as exc:
                findings.append(_finding("syntax_error", relative, {"line": exc.lineno, "message": exc.msg}))
        elif path.suffix == ".json":
            if _is_jsonc(Path(relative)):
                continue
            try:
                documents[relative] = json.loads(text)
            except json.JSONDecodeError as exc:
                findings.append(_finding("invalid_json", relative, {"line": exc.lineno, "message": exc.msg}))
        elif path.suffix == ".toml":
            try:
                documents[relative] = tomllib.loads(text)
            except tomllib.TOMLDecodeError as exc:
                findings.append(_finding("invalid_toml", relative, {"message": str(exc)}))
        else:
            try:
                documents[relative] = yaml.safe_load(text)
            except yaml.YAMLError as exc:
                findings.append(_finding("invalid_yaml", relative, {"message": str(exc)}))
        if match := _SECRET.search(text):
            findings.append(_finding("hardcoded_secret", relative, {"line": text[:match.start()].count("\n") + 1, "field": match.group("field").lower()}))
    contexts = _project_contexts(root, documents)
    contexts_by_file = {relative: _context_for_path(root, relative, contexts) for relative, _ in parsed_python}
    known_modules_by_context: dict[ProjectContext, set[str]] = {context: set() for context in contexts}
    for relative, _ in parsed_python:
        context = contexts_by_file[relative]
        if context is not None:
            known_modules_by_context[context].update(_module_names(root, relative, context.root))
    findings.extend(_local_import_findings(parsed_python, contexts_by_file, known_modules_by_context))
    findings.extend(_dependency_findings(parsed_python, contexts_by_file, known_modules_by_context))
    findings.extend(_schema_reference_findings(root, documents))
    findings.extend(_entrypoint_findings(root, contexts, contents))
    by_content: dict[str, list[str]] = {}
    for relative, text in contents.items():
        normalized = "\n".join(line.strip() for line in text.splitlines() if line.strip())
        if len(normalized) >= 20:
            by_content.setdefault(hashlib.sha256(normalized.encode("utf-8")).hexdigest(), []).append(relative)
    for paths in by_content.values():
        if len(paths) > 1:
            for relative in sorted(paths):
                findings.append(_finding("duplicate_implementation", relative, {"duplicate_files": sorted(paths)}))
    for symbol, paths in symbols.items():
        if len(paths) > 1:
            for relative in sorted(paths):
                findings.append(_finding("overlapping_symbol", relative, {"symbol": symbol, "overlapping_files": sorted(paths)}))
    baseline_metadata, drift_findings = _baseline(root, baseline)
    findings.extend(drift_findings)
    findings = sorted({item["id"]: item for item in findings}.values(), key=lambda item: (item["file"], item["type"], item["id"]))
    counts = Counter(item["type"] for item in findings)
    return ScanReport("1.0.0", str(root), baseline_metadata, findings, {"finding_count": len(findings), "finding_types": dict(sorted(counts.items())), "registry_types": sorted(FINDING_REGISTRY)})


def scan(root: Path) -> list[dict[str, Any]]:
    return scan_report(root).findings


def issue_paths(issue: str, root: Path) -> set[str]:
    return {candidate for candidate in _PATH.findall(issue) if (root / candidate).is_file()}
