from __future__ import annotations

import ast
from collections import deque
from pathlib import Path
import tomllib
from typing import Any, Mapping

from .artifacts import ArtifactError, canonical_hash, verify_artifact, verify_current_snapshot
from .scanner import ProjectContext, _context_for_path, _module_names, _project_contexts, issue_paths, supported_paths


_MAX_SEEDS = 256


def _relative_import(module: str | None, level: int, importer: str, root: Path, context: ProjectContext) -> str | None:
    if not level:
        return module
    parts = list((root / importer).relative_to(context.root).with_suffix("").parts)
    package = parts[:-1] if parts[-1] != "__init__" else parts[:-1]
    keep = len(package) - level + 1
    if keep < 0:
        return None
    target = package[:keep]
    if module:
        target.extend(module.split("."))
    return ".".join(target) or None


def _local_target(module: str | None, known_modules: Mapping[str, str]) -> str | None:
    if not module:
        return None
    candidate = module
    while candidate:
        if candidate in known_modules:
            return known_modules[candidate]
        candidate = candidate.rpartition(".")[0]
    return None


def _call_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        return f"{node.value.id}.{node.attr}"
    return None


def _reachable(start: str, edges_by_parent: Mapping[str, set[str]]) -> set[str]:
    seen: set[str] = set()
    queue = deque([start])
    while queue:
        current = queue.popleft()
        if current in seen:
            continue
        seen.add(current)
        queue.extend(sorted(edges_by_parent.get(current, set()) - seen))
    return seen


def trace_inspection(inspection: Mapping[str, Any]) -> dict[str, Any]:
    """Build a bounded static impact graph without changing the inspected repository."""
    verify_artifact(inspection, "audisor.inspection", "manifest_sha256")
    root_value = inspection.get("repository_root")
    snapshot = inspection.get("source_snapshot")
    report = inspection.get("scan_report")
    original_issue = inspection.get("original_issue")
    if not isinstance(root_value, str) or not isinstance(snapshot, list) or not isinstance(report, Mapping) or not isinstance(original_issue, str):
        raise ArtifactError("trace_fields_invalid")
    root = Path(root_value)
    if not root.is_dir():
        raise ArtifactError("repository_not_found")
    verify_current_snapshot(root, snapshot)

    contents: dict[str, str] = {}
    documents: dict[str, Any] = {}
    parsed: dict[str, ast.Module] = {}
    for path in supported_paths(root):
        relative = path.relative_to(root).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        contents[relative] = text
        if path.suffix == ".py":
            try:
                parsed[relative] = ast.parse(text, filename=relative)
            except SyntaxError:
                continue
        elif path.name == "pyproject.toml":
            try:
                documents[relative] = tomllib.loads(text)
            except tomllib.TOMLDecodeError:
                continue

    contexts = _project_contexts(root, documents)
    context_by_file = {relative: _context_for_path(root, relative, contexts) for relative in parsed}
    known_modules: dict[ProjectContext, dict[str, str]] = {context: {} for context in contexts}
    for relative, context in context_by_file.items():
        if context is None:
            continue
        for module in _module_names(root, relative, context.root):
            known_modules[context][module] = relative

    edges: list[dict[str, Any]] = []
    dependencies: dict[str, set[str]] = {relative: set() for relative in parsed}
    dynamic_uncertainties: list[dict[str, Any]] = []
    for relative, tree in parsed.items():
        context = context_by_file[relative]
        if context is None:
            continue
        modules = known_modules[context]
        for node in ast.walk(tree):
            imported: list[tuple[str | None, int]] = []
            if isinstance(node, ast.Import):
                imported.extend((alias.name, 0) for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.append((node.module, node.level))
            for module, level in imported:
                target = _local_target(_relative_import(module, level, relative, root, context), modules)
                if target and target != relative:
                    dependencies[relative].add(target)
                    edges.append({"from": relative, "to": target, "kind": "static_import", "line": node.lineno})
            if isinstance(node, ast.Call) and _call_name(node.func) in {"__import__", "importlib.import_module"}:
                argument = node.args[0] if node.args else None
                if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                    target = _local_target(argument.value, modules)
                    if target and target != relative:
                        dependencies[relative].add(target)
                        edges.append({"from": relative, "to": target, "kind": "dynamic_import_literal", "line": node.lineno})
                else:
                    dynamic_uncertainties.append({"file": relative, "line": node.lineno, "reason": "dynamic_import_target_not_static"})

    parents: dict[str, set[str]] = {relative: set() for relative in parsed}
    for parent, children in dependencies.items():
        for child in children:
            parents.setdefault(child, set()).add(parent)

    issue_seed_paths = issue_paths(original_issue.replace("\\", "/"), root)
    finding_seed_paths = {
        item.get("file")
        for item in report.get("findings", [])
        if isinstance(item, Mapping) and isinstance(item.get("file"), str) and item.get("file") in parsed
    }
    requested_seeds = sorted(issue_seed_paths | finding_seed_paths)
    seeds = requested_seeds[:_MAX_SEEDS]
    uncertainties = dynamic_uncertainties[:]
    if len(requested_seeds) > _MAX_SEEDS:
        uncertainties.append({"reason": "seed_limit_reached", "requested_seed_count": len(requested_seeds), "included_seed_count": _MAX_SEEDS})

    entrypoints: list[dict[str, Any]] = []
    for context in contexts:
        for script, target in context.scripts:
            module = target.partition(":")[0]
            file = _local_target(module, known_modules[context])
            entrypoints.append({"script": script, "target": target, "file": file, "project_root": context.root.relative_to(root).as_posix()})

    test_files = {relative for relative in parsed if Path(relative).name.startswith("test_") or "/tests/" in f"/{relative}"}
    seed_details: list[dict[str, Any]] = []
    for seed in seeds:
        transitive_parents = _reachable(seed, parents) - {seed}
        direct_tests = sorted(parents.get(seed, set()) & test_files)
        reached_by_entrypoints = sorted(
            entrypoint["script"]
            for entrypoint in entrypoints
            if isinstance(entrypoint.get("file"), str) and seed in _reachable(str(entrypoint["file"]), dependencies)
        )
        context = context_by_file.get(seed)
        seed_details.append(
            {
                "file": seed,
                "project_root": context.root.relative_to(root).as_posix() if context else None,
                "direct_dependencies": sorted(dependencies.get(seed, set())),
                "direct_parents": sorted(parents.get(seed, set())),
                "transitive_parents": sorted(transitive_parents),
                "direct_test_importers": direct_tests,
                "reached_by_entrypoints": reached_by_entrypoints,
            }
        )

    artifact: dict[str, Any] = {
        "artifact_type": "audisor.trace",
        "schema_version": "1.0.0",
        "inspection_manifest_sha256": inspection["manifest_sha256"],
        "seed_details": seed_details,
        "edges": sorted(edges, key=lambda item: (item["from"], item["to"], item["line"], item["kind"])),
        "entrypoints": sorted(entrypoints, key=lambda item: (item["project_root"], item["script"])),
        "uncertainties": sorted(uncertainties, key=lambda item: (str(item.get("file", "")), int(item.get("line", 0)), str(item.get("reason", "")))),
    }
    artifact["trace_sha256"] = canonical_hash(artifact, "trace_sha256")
    return artifact
