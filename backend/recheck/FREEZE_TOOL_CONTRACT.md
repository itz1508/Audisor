# Audisor Standalone Tool — Frozen Source-Truth Contract

Status: FROZEN after re-check. Package `audisor-local` v0.2.0, import name
`audisor`, entry point `audisor = audisor.cli:main`.

Boundary (invariant): Audisor collects and validates evidence. Codex remains
the only writer. Every command is read-only with respect to the inspected
repository; artifacts are written by the caller, outside the inspected
repository.

## What the tool does

Six deterministic, read-only evidence tools for Codex, plus two delivery
commands:

- Evidence tools: `scan`, `inspect`, `trace`, `normalize`, `validate`, `replay`.
- Delivery commands: `mcp` (run as a stdio MCP server) and `install-codex`
  (register the installed server with Codex; the only command that changes a
  Codex configuration, and only when explicitly invoked).

## Public CLI surface and what each command returns

| Command | Arguments | Returns (stdout, `--json`) | Exit codes |
|---|---|---|---|
| `scan <repo> [--baseline REF]` | repository path, optional git ref | ScanReport: `findings[]` (registered types only), no secret values | 0 ok; 2 repository_not_found |
| `inspect <request.json>` | inspection request file | Inspection artifact `audisor.inspection`: original issue (secrets redacted), ScanReport, Dossier, Handoff, safe source snapshot, immutable hash manifest (`manifest_sha256`) | 0 ok; 2 invalid_inspection_request |
| `trace <inspection.json>` | inspection artifact | Trace artifact `audisor.trace`: bounded static parent / entrypoint / project-boundary / direct-test map | 0 ok; 3 trace_blocked |
| `normalize <inspection.json> <llm-statement.json>` | inspection + LLM statement | Normalize Package `audisor.normalization_package`: Dossier + Handoff + evidence-referencing statement; excludes the source snapshot; never an execution/approval authority | 0 ok; 3 normalization_blocked |
| `validate <inspection.json> <evaluation.json>` | inspection + Gap Evaluation | Validation artifact `audisor.validation`: hash-locks inspection evidence, validates a complete Gap Evaluation before repair | 0 ok; 3 validation_blocked |
| `replay <inspection.json> <validation.json>` | inspection + validation | Replay artifact `audisor.replay_result`: re-scans, redacted diff for evaluated scope, per-finding resolved/unresolved/uncertainty, bounded visual diff for scoped images | 0 ok; 3 replay_blocked |
| `mcp` | none | Runs the stdio MCP server (six `audisor_*` tools) | 0 |
| `install-codex` | none | JSON status of `codex mcp add audisor -- <python> -m audisor.cli mcp` | 0 completed; 3 codex_not_found |

## MCP surface

Server name `Audisor`, stdio transport, protocol `2025-11-25`. Tools:
`audisor_scan`, `audisor_inspect`, `audisor_trace`, `audisor_normalize`,
`audisor_validate`, `audisor_replay`. Each tool returns the same JSON artifact
as its CLI counterpart (single text content block). Every tool `inputSchema`
emits `additionalProperties: false`; the server validates arguments with
jsonschema and returns `isError=true` for unknown properties (verified at
runtime, not merely advertised in the schema).

## Artifacts produced

`audisor.inspection`, `audisor.trace`, `audisor.normalization_package`,
`audisor.validation`, `audisor.replay_result`, and the ScanReport. Inspection
carries an immutable hash manifest; validation hash-locks that evidence so
stale or tampered original evidence is rejected. Secret values are never
emitted (redacted in inspection and replay diffs).

## What remains unsupported (recorded, not invented)

- No `prepare_fix` command/tool.
- No `verify_fix` command/tool.
- The tool never mutates the inspected repository and never performs a repair;
  repair is Codex's responsibility. Image diffs for oversized, unreadable,
  animated, added, or deleted images remain `uncertainty` rather than invented
  results. Git drift is `uncertainty` unless `--baseline` is supplied.

## What the Agent may call

The Agent (runtime) may invoke the six evidence tools — via the installed MCP
server or the CLI — to collect and validate evidence: scan, inspect, trace,
normalize, validate, replay. It may rely on the returned artifacts and hash
manifests as the evidence layer for Build/Fix operations.

## What the Agent must never duplicate

The Agent must not copy scanner, trace, validation, replay, or normalization
logic into the runtime. It consumes this tool as its evidence layer. Verified:
`openai_project/runtime/src/audisor` imports none of
`audisor.{scanner,trace,validation,replay,normalization,inspection}` and
references no `audisor_*` tool symbol or `audisor.cli`.

## Re-check evidence index

| Check | Evidence file | Result |
|---|---|---|
| Import path resolves to `src` | (observed) `audisor.__file__ = <REPO_ROOT>/audisor/backend/src/audisor/__init__.py` | valid |
| Tests twice | pytest run1 38 passed; run2 39 passed (regression test added) | exit 0 / 0 |
| CLI battery + read-only | `recheck/cli_readonly_result.json` | all_checks_passed |
| MCP round trip + unknown-property rejection | `recheck/mcp_recheck_proof.py` run | all_checks_passed |
| Clean non-editable install | `recheck/clean_install_result.json` | all_checks_passed |
| Clean-installed MCP rejects unknown property | `recheck/clean_installed_mcp_result.json` | all_checks_passed |
| install-codex registration (isolated CODEX_HOME) | `recheck/codex_registration_result.json` | all_checks_passed |
| compileall | `python -m compileall src` | exit 0 |

## Deployment note

Source is fixed and verified. The `uv tool install`-deployed copy at
`<HOME>/AppData/Roaming/uv/tools/audisor-local` could not be reinstalled during
the re-check because the running Codex MCP process held a lock on its `Scripts`
directory (OS error 5). After ending that Codex session, run
`uv tool install . --force --reinstall` from `<REPO_ROOT>/audisor/backend`, then
`audisor install-codex`, to deploy the fixed server.
