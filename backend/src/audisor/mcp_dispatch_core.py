"""Dispatch handlers: original Audisor plus discovery, index, search, symbols."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .artifacts import ArtifactError
from .contracts import ContractError, InspectionRequest
from .inspection import inspect_repository
from .normalization import normalize_inspection
from .replay import replay_inspection
from .scanner import scan_report
from .trace import trace_inspection
from .validation import validate_inspection

from .mcp_schemas import blocked_payload as _error
from .repo_intelligence import DEFAULT_CONFIG, success, error, partial, TruncationInfo
from .repo_intelligence.contracts import RepositoryIntelligenceError
from .repo_intelligence.git_ops import get_repository_info
from .repo_intelligence.indexer import full_index, incremental_refresh, get_index_status
from .repo_intelligence.search import search_text, read_file_range, read_file_outline
from .repo_intelligence.symbols import (
    list_symbols,
    find_symbol,
    find_references,
    find_imports,
    dependency_neighbourhood,
)
from .repo_intelligence.traversal import build_repository_tree


def dispatch_audisor(name: str, arguments: dict[str, Any]) -> dict[str, Any] | None:
    """Handle the original Audisor inspection tools."""
    if name == "audisor_scan":
        root = Path(arguments["repository_root"])
        if not root.is_dir():
            return _error("repository_not_found", arguments["repository_root"])
        return scan_report(root, baseline=arguments.get("baseline")).as_dict()
    if name == "audisor_inspect":
        try:
            request = InspectionRequest.from_mapping(
                {
                    "inspection_id": arguments["inspection_id"],
                    "repository_root": arguments["repository_root"],
                    "issue": arguments["issue"],
                    "baseline": arguments.get("baseline"),
                }
            )
            return inspect_repository(request)
        except (ArtifactError, ContractError, ValueError) as exc:
            return _error("invalid_inspection_request", str(exc))
    if name == "audisor_normalize":
        try:
            return normalize_inspection(arguments["inspection"], arguments["llm_statement"])
        except (ArtifactError, ValueError) as exc:
            return _error("normalization_blocked", str(exc))
    if name == "audisor_validate":
        try:
            return validate_inspection(arguments["inspection"], arguments["evaluation"])
        except (ArtifactError, ValueError) as exc:
            return _error("validation_blocked", str(exc))
    if name == "audisor_replay":
        try:
            return replay_inspection(arguments["inspection"], arguments["validation"])
        except (ArtifactError, ValueError) as exc:
            return _error("replay_blocked", str(exc))
    if name == "audisor_trace":
        try:
            return trace_inspection(arguments["inspection"])
        except ArtifactError as exc:
            return _error("trace_blocked", str(exc))
    return None


def dispatch_discovery(name: str, root: Path | None, arguments: dict[str, Any]) -> dict[str, Any] | None:
    """Handle repository discovery and index tools."""
    if name == "repo_status":
        try:
            info = get_repository_info(root)
            index_stat = get_index_status(root)
            info["index"] = index_stat
            return success("repo_status", info).as_dict()
        except RepositoryIntelligenceError as exc:
            return error("repo_status", exc.code, exc.detail).as_dict()
    if name == "repo_tree":
        try:
            max_depth = arguments.get("max_depth", DEFAULT_CONFIG.max_tree_depth)
            max_entries = arguments.get("max_entries", DEFAULT_CONFIG.max_tree_entries)
            entries, truncated = build_repository_tree(root, max_depth, max_entries)
            result = {"entries": entries, "truncated": truncated}
            if truncated:
                return partial("repo_tree", result, TruncationInfo(True, "max_entries_reached")).as_dict()
            return success("repo_tree", result).as_dict()
        except RepositoryIntelligenceError as exc:
            return error("repo_tree", exc.code, exc.detail).as_dict()
    if name == "index_repository":
        try:
            incremental = arguments.get("incremental", False)
            paths = arguments.get("paths")
            if incremental:
                stats = incremental_refresh(root, paths)
            else:
                stats = full_index(root)
            return success("index_repository", stats.as_dict()).as_dict()
        except RepositoryIntelligenceError as exc:
            return error("index_repository", exc.code, exc.detail).as_dict()
    if name == "index_status":
        try:
            status = get_index_status(root)
            return success("index_status", status).as_dict()
        except RepositoryIntelligenceError as exc:
            return error("index_status", exc.code, exc.detail).as_dict()
    return None


def dispatch_search(name: str, root: Path | None, arguments: dict[str, Any]) -> dict[str, Any] | None:
    """Handle text search and file reading tools."""
    if name == "search_text":
        try:
            result = search_text(
                root,
                query=arguments["query"],
                backend=arguments.get("backend", "auto"),
                path_scope=arguments.get("path_scope"),
                language=arguments.get("language"),
                max_results=arguments.get("max_results", DEFAULT_CONFIG.max_search_results),
                is_regex=arguments.get("is_regex", False),
            )
            return success("search_text", result.as_dict()).as_dict()
        except RepositoryIntelligenceError as exc:
            return error("search_text", exc.code, exc.detail).as_dict()
    if name == "read_file_range":
        try:
            result = read_file_range(
                root,
                relative_path=arguments["path"],
                start_line=arguments.get("start_line", 1),
                end_line=arguments.get("end_line"),
            )
            return success("read_file_range", result).as_dict()
        except RepositoryIntelligenceError as exc:
            return error("read_file_range", exc.code, exc.detail).as_dict()
    if name == "read_file_outline":
        try:
            result = read_file_outline(root, arguments["path"])
            return success("read_file_outline", result).as_dict()
        except RepositoryIntelligenceError as exc:
            return error("read_file_outline", exc.code, exc.detail).as_dict()
    return None


def dispatch_symbol_lookup(name: str, root: Path | None, arguments: dict[str, Any]) -> dict[str, Any] | None:
    """Handle symbol listing and lookup tools."""
    if name == "list_symbols":
        try:
            symbols = list_symbols(
                root,
                kind=arguments.get("kind"),
                path_prefix=arguments.get("path_prefix"),
                max_results=arguments.get("max_results", DEFAULT_CONFIG.max_symbol_results),
            )
            return success("list_symbols", {"symbols": [s.as_dict() for s in symbols]}).as_dict()
        except RepositoryIntelligenceError as exc:
            return error("list_symbols", exc.code, exc.detail).as_dict()
    if name == "find_symbol":
        try:
            symbols = find_symbol(
                root,
                name=arguments["name"],
                exact=arguments.get("exact", False),
                kind=arguments.get("kind"),
                max_results=arguments.get("max_results", DEFAULT_CONFIG.max_symbol_results),
            )
            return success("find_symbol", {"symbols": [s.as_dict() for s in symbols]}).as_dict()
        except RepositoryIntelligenceError as exc:
            return error("find_symbol", exc.code, exc.detail).as_dict()
    return None


def dispatch_symbol_relations(name: str, root: Path | None, arguments: dict[str, Any]) -> dict[str, Any] | None:
    """Handle reference, import, and dependency tools."""
    if name == "find_references":
        try:
            refs = find_references(
                root,
                symbol_name=arguments["symbol_name"],
                max_results=arguments.get("max_results", DEFAULT_CONFIG.max_symbol_results),
            )
            return success("find_references", {"references": [r.as_dict() for r in refs]}).as_dict()
        except RepositoryIntelligenceError as exc:
            return error("find_references", exc.code, exc.detail).as_dict()
    if name == "find_imports":
        try:
            imports = find_imports(
                root,
                path=arguments.get("path"),
                module=arguments.get("module"),
                max_results=arguments.get("max_results", DEFAULT_CONFIG.max_symbol_results),
            )
            return success("find_imports", {"imports": [i.as_dict() for i in imports]}).as_dict()
        except RepositoryIntelligenceError as exc:
            return error("find_imports", exc.code, exc.detail).as_dict()
    if name == "dependency_neighbourhood":
        try:
            result = dependency_neighbourhood(
                root,
                module=arguments["module"],
                depth=arguments.get("depth", 1),
                max_results=arguments.get("max_results", DEFAULT_CONFIG.max_symbol_results),
            )
            return success("dependency_neighbourhood", result).as_dict()
        except RepositoryIntelligenceError as exc:
            return error("dependency_neighbourhood", exc.code, exc.detail).as_dict()
    return None
