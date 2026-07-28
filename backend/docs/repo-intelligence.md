# Repository Intelligence Toolkit

A persistent local repository-intelligence layer for the Audisor MCP server.
Provides indexing, search, symbol intelligence, git operations, command execution,
and safe mutation capabilities.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           MCP Server (mcp_server.py)                     │
│  35 tools: 6 original + 29 repository intelligence tools                │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
        ┌───────────────────────────┼───────────────────────────┐
        │                           │                           │
        ▼                           ▼                           ▼
┌───────────────┐          ┌───────────────┐          ┌───────────────┐
│   Discovery   │          │     Index     │          │    Search     │
│  repo_status  │          │ index_repo    │          │  search_text  │
│   repo_tree   │          │ index_status  │          │ read_file_range│
│               │          │ refresh_paths │          │read_file_outline│
└───────────────┘          └───────────────┘          └───────────────┘
        │                           │                           │
        ▼                           ▼                           ▼
┌───────────────┐          ┌───────────────┐          ┌───────────────┐
│   Symbols     │          │      Git      │          │   Commands    │
│  list_symbols │          │  git_status   │          │  run_command  │
│  find_symbol  │          │   git_diff    │          │run_validation │
│find_references│          │ git_history   │          │operation_status│
│  find_imports │          │git_show_file  │          │               │
│dep_neighbourhood│        │               │          │               │
└───────────────┘          └───────────────┘          └───────────────┘
        │                           │                           │
        ▼                           ▼                           ▼
┌───────────────┐          ┌───────────────┐          ┌───────────────┐
│ Diagnostics   │          │   Mutation    │          │  Operations   │
│parse_test_fail│          │ prepare_patch │          │ create_operation│
│parse_traceback│          │  apply_patch  │          │ start_operation│
│summarise_failure│        │               │          │complete_operation│
└───────────────┘          └───────────────┘          │ fail_operation │
                                                      └───────────────┘
```

## Index Location and Repository Identity

### Index Database Location

The index database is stored at:
```
<repository_root>/.audisor/repo-intelligence.db
```

This location is:
- **Gitignored**: The `.audisor/` directory is excluded from version control
- **Untracked**: Not part of the repository's working tree
- **Safe to delete**: Can be removed at any time; will be recreated on next index
- **Excluded from indexing**: The index does not index itself

### Repository Identity

The repository is identified by its resolved absolute path, stored in the
`index_metadata` table. This ensures:
- Each repository has its own isolated index
- Moving the repository invalidates the index (requires re-index)
- Multiple repositories can coexist with separate indices

### Operation State

Operations are persisted in the `operations` table within the same SQLite database.
Operation state:
- Persists across process restarts
- Is tied to the repository (not the process)
- Can be queried via `operation_status` and `operation_result` tools
- Is safe to delete (removes operation history but not index data)

## Exclusions

The following paths are excluded from indexing:

### Hard Safety Exclusions
- `.git/` - Git metadata
- `.venv/`, `venv/` - Virtual environments
- `node_modules/` - Node.js dependencies
- `dist/`, `build/` - Build outputs
- `__pycache__/` - Python bytecode cache
- `.pytest_cache/` - Pytest cache
- `.audisor/` - Audisor's own state (including the index itself)

### Binary File Detection
Files are detected as binary and skipped if they:
- Contain null bytes in the first 8KB
- Have binary file extensions (`.png`, `.jpg`, `.exe`, etc.)

### Credential File Detection
Files matching credential patterns are excluded:
- `.env`, `.env.local`, `.env.*`
- `secrets.yaml`, `secrets.yml`
- `*.pem`, `*.key`

## Incremental Refresh

The `incremental_refresh` function:
1. Compares file hashes against the index
2. Only reparses files whose content has changed
3. Updates FTS5 index for changed files only
4. Records statistics about files examined, reparsed, skipped

### Known Limitations

**Deletion and Rename Detection**: The current incremental refresh does NOT
automatically detect file deletions or renames. Stale records remain in the
index until a full re-index is performed. To clean up stale records:

```bash
# Full re-index to remove stale records
index_repository(repository_root, incremental=False)
```

## FTS5 Tokenizer

The FTS5 index uses the `unicode61` tokenizer, which:
- Tokenizes on whitespace and punctuation
- Lowercases all tokens
- Handles Unicode correctly

### Tokenization Behavior

| Input | Tokens |
|-------|--------|
| `my_function_name` | `my`, `function`, `name` |
| `os.path.join` | `os`, `path`, `join` |
| `/usr/local/bin` | `usr`, `local`, `bin` |
| `my-hyphenated-name` | `my`, `hyphenated`, `name` |

### Search Examples

```python
# Exact identifier search
search_text(root, "exact_identifier", backend="index")

# Partial identifier search
search_text(root, "function", backend="index")  # Matches my_function_name

# Path search
search_text(root, "usr", backend="index")  # Matches /usr/local/bin
```

## Semantic Limitations

### find_references

The `find_references` tool provides confidence-labeled reference finding:
- `definition` - Symbol definition location
- `import` - Import statement
- `ast_reference` - AST-based reference (not implemented, falls back to lexical)
- `lexical_reference` - FTS5-based lexical match

**This is NOT full LSP semantic resolution.** It does not:
- Track symbol renames across files
- Understand type inference
- Resolve dynamic imports
- Handle metaprogramming

For full semantic resolution, use an LSP server.

## Command Policy

### Argument Array Execution

Commands are executed as argument arrays, NOT shell strings:
```python
# Correct
run_command(root, ["uv", "run", "python", "-m", "pytest"])

# Incorrect (shell interpolation risk)
run_command(root, "uv run python -m pytest")
```

### Working Directory Containment

The `working_directory` parameter must be relative to the repository root.
Absolute paths or paths escaping the repository are rejected.

### Timeout and Process Tree Termination

Commands have a configurable timeout (default: 300 seconds). On timeout:
- **Windows**: Uses `taskkill /T` to terminate the entire process tree
- **Unix**: Uses process group kill (`killpg`)

### Output Truncation

Command output is truncated to `max_output_bytes` (default: 1MB).
Truncation is indicated in the result metadata.

### Validation Profiles

Validation profiles are derived from repository inspection:

| Profile | Command | Working Directory |
|---------|---------|-------------------|
| `focused` | `uv run python -m pytest -x -v {path}` | Repository root |
| `runtime` | `uv run --directory openai_project/runtime pytest tests/audisor_lifecycle/` | `openai_project/runtime` |
| `backend` | `uv run --directory audisor/backend pytest tests/` | `audisor/backend` |
| `aflow` | `uv run --directory audisor/backend pytest tests/ -k aflow` | `audisor/backend` |
| `scripts` | `uv run pytest scripts/tests/` | Repository root |
| `fixtures` | `uv run --directory audisor/backend pytest tests/ -k fixture` | `audisor/backend` |
| `size` | `uv run python scripts/check_size.py` | Repository root |
| `build` | `uv build --directory audisor/backend` | `audisor/backend` |
| `compile` | `uv run --directory audisor/backend python -m compileall src/audisor/repo_intelligence/` | `audisor/backend` |

### Bare Python Commands

The validation profiles use `uv run python` which is the recommended approach.
Bare `python`, `python3`, or `py` commands are not explicitly rejected but
are not recommended. Use `uv run python` for consistency.

## Prepare/Apply Boundary

### prepare_patch (Preview Only)

The `prepare_patch` tool:
- Validates path security
- Computes SHA-256 hash of current file
- Generates unified diff
- **Does NOT modify the file**
- Returns preview with diff, original hash, new hash

### apply_patch (Mutation)

The `apply_patch` tool:
- Re-validates path security
- Re-validates current file hash against `expected_sha256`
- Writes new content atomically (temp file + rename)
- **Does NOT stage or commit** (leaves file in modified state)
- Returns result with new hash

### Hash Verification

The `expected_sha256` parameter prevents stale patches:
1. Call `prepare_patch` to get current hash
2. Call `apply_patch` with that hash
3. If file changed between prepare and apply, apply fails with `hash_mismatch`

### Atomic Writes

File writes use the atomic pattern:
1. Write to temporary file in same directory
2. `os.replace()` to atomically swap
3. Ensures no partial writes on crash

### Line Ending Preservation

Line endings are preserved as-is. The patch content should match the file's
existing line ending style (LF or CRLF).

## Start Command

Start the MCP server:

```bash
cd audisor/backend
uv run python -m audisor.cli mcp
```

## Rebuild/Delete Instructions

### Rebuild Index

```python
# Full re-index (clears and rebuilds)
index_repository(repository_root, incremental=False)

# Incremental refresh (only changed files)
index_repository(repository_root, incremental=True)

# Refresh specific paths
refresh_paths(repository_root, paths=["src/module.py", "tests/test_module.py"])
```

### Delete Index

```bash
# Delete the index database
rm -rf <repository_root>/.audisor/repo-intelligence.db

# Or delete the entire .audisor directory
rm -rf <repository_root>/.audisor/
```

The index will be recreated on the next `index_repository` call.

## Windows uv Requirement

The validation profiles require `uv` to be installed and available in PATH.
On Windows:

```powershell
# Install uv
pip install uv

# Or use the standalone installer
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

All validation commands use `uv run` to ensure consistent Python environment.

## Usage Examples

### Basic Indexing

```python
from audisor.mcp_server import _dispatch

# Index repository
result = _dispatch("index_repository", {
    "repository_root": "/path/to/repo",
    "incremental": False
})
print(result)

# Check index status
result = _dispatch("index_status", {
    "repository_root": "/path/to/repo"
})
print(result)
```

### Search

```python
# Text search
result = _dispatch("search_text", {
    "repository_root": "/path/to/repo",
    "query": "function_name",
    "backend": "index"
})

# Read file range
result = _dispatch("read_file_range", {
    "repository_root": "/path/to/repo",
    "path": "src/module.py",
    "start_line": 10,
    "end_line": 20
})
```

### Symbol Intelligence

```python
# List all symbols
result = _dispatch("list_symbols", {
    "repository_root": "/path/to/repo"
})

# Find references
result = _dispatch("find_references", {
    "repository_root": "/path/to/repo",
    "symbol_name": "MyClass"
})
```

### Safe Mutation

```python
# Prepare patch (preview)
preview = _dispatch("prepare_patch", {
    "repository_root": "/path/to/repo",
    "path": "src/module.py",
    "new_content": "# new content"
})
print(preview["result"]["original_sha256"])

# Apply patch (mutation)
result = _dispatch("apply_patch", {
    "repository_root": "/path/to/repo",
    "path": "src/module.py",
    "new_content": "# new content",
    "expected_sha256": preview["result"]["original_sha256"]
})
```

## Tool Inventory

### Original Audisor Tools (6)
- `audisor_scan` - Create deterministic scan report
- `audisor_inspect` - Create immutable evidence snapshot
- `audisor_normalize` - Normalize inspection with LLM statement
- `audisor_validate` - Validate inspection against evaluation
- `audisor_replay` - Replay inspection with validation
- `audisor_trace` - Trace inspection dependencies

### Discovery Tools (2)
- `repo_status` - Repository metadata and index status
- `repo_tree` - Repository tree structure

### Index Tools (3)
- `index_repository` - Full or incremental index
- `index_status` - Index metadata and statistics
- `refresh_paths` - Refresh specific paths in index

### Search Tools (3)
- `search_text` - Text search (FTS5 or ripgrep)
- `read_file_range` - Read file line range
- `read_file_outline` - File structural outline

### Symbol Tools (5)
- `list_symbols` - List all symbols
- `find_symbol` - Find symbol by name
- `find_references` - Find symbol references with confidence
- `find_imports` - Find import relationships
- `dependency_neighbourhood` - Find module dependencies

### Git Tools (4)
- `git_status` - Structured git status
- `git_diff` - Git diff with filters
- `git_history` - Commit history
- `git_show_file` - File from historical revision

### Command Tools (3)
- `run_command` - Execute command with timeout
- `run_validation` - Run validation profile
- `operation_status` - Get operation status

### Operation Tools (1)
- `operation_result` - Get completed operation result

### Diagnostic Tools (3)
- `parse_test_failures` - Parse pytest output
- `parse_python_traceback` - Parse Python traceback
- `summarise_command_failure` - Deterministic failure summary

### Mutation Tools (2)
- `prepare_patch` - Preview patch without mutation
- `apply_patch` - Apply patch with hash verification

### Gap Analysis Tools (3)
- `create_gap` - Initialize a gap analysis run
- `find_gap` - Read-only evidence-based gap analysis
- `gap_record` - Persist a gap analysis record

**Total: 35 tools**

## Known Limitations

1. **Detached operation execution is not implemented**
   - Operations are tracked in SQLite with status (queued, running, completed, failed, timed_out, cancelled)
   - However, indexing and validation run synchronously within the MCP request
   - The operation ID is returned after work completes, not before
   - **This is an unresolved required capability** for true long-running operations
   - Workaround: Use operation tracking for command execution (which is synchronous but tracked)

2. **find_references is not full LSP semantic resolution**
   - Uses FTS5 lexical matching, not type inference
   - May miss dynamic imports or metaprogramming
   - Workaround: Use an LSP server for full semantic resolution

3. **FTS5 tokenizer splits on punctuation**
   - `my_function` becomes tokens `my`, `function`
   - Exact phrase search requires quotes
   - Workaround: Use `escape_fts5_query` for exact matches

4. **Search backend selection may fall back silently**
   - FTS5 is preferred, ripgrep is fallback
   - If FTS5 is unavailable, ripgrep is used without explicit notification
   - Workaround: Check index metadata to verify FTS5 is enabled

5. **Changed-file accounting does not enumerate untracked files**
   - `git_status` reports counts but not full file lists for untracked/modified
   - Workaround: Use `git status --porcelain` directly for full enumeration

## Testing

Run all tests:
```bash
cd audisor/backend
uv run pytest tests/
```

Run specific test suites:
```bash
# Repository intelligence tests
uv run pytest tests/repo_intelligence/

# Closure and correction tests
uv run pytest tests/repo_intelligence/test_closure.py

# Post-build fixture tests
uv run pytest tests/repo_intelligence/test_post_build_fixtures.py

# MCP server tests
uv run pytest tests/test_mcp.py
```

## Size Checker

Check repository size:
```bash
cd audisor/backend
uv run python scripts/check_size.py
```

The size checker validates:
- Total repository size
- Individual file sizes
- Directory sizes
- Excluded path sizes

## License

Same as the parent Audisor project.
