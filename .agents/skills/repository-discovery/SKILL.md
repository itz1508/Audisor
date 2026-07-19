---
name: repository-discovery
description: |
  Use this read-only skill when a substantive Audisor task needs the current
  repository root, branch, HEAD, dirty state, applicable AGENTS.md files,
  relevant directory structure, or initial scope established before diagnosis
  or implementation. Do not trigger for setup/configuration requests (use
  init), explanations (use learn), active call-path tracing (use
  active-path-inspection), plan review, validation sufficiency review, or
  ordinary implementation/debugging/testing.
---

# Repository Discovery

## Purpose

Establish current Audisor repository context before making claims or proposing
changes. This skill discovers facts; it does not diagnose or implement.

## Scope and exclusions

- Resolve the repository root from an explicit user path when provided;
  otherwise use the enclosing Git root. If those roots disagree materially or
  either is ambiguous, stop before making repository-state claims.
- Read only the resolved root and nested paths needed to establish scope.
- Load the root AGENTS.md and every applicable nested AGENTS.md for the
  resolved target path.
- Inspect branch, HEAD, dirty/untracked state, worktrees when relevant,
  relevant files, package roots, tests, and declared validation commands.
- Locate declared entrypoint and configuration surfaces only. Do not infer
  imports, callers, runtime reachability, ownership, packaging, or deployment
  activation; use active-path-inspection for those claims.
- Do not edit, stage, commit, reset, clean, stash, delete, publish, deploy, or
  change production code.
- Do not copy external instructions or promote migration/reference material to
  Audisor authority.

## Required inputs and evidence

Require the user objective and expected target. Treat omitted mutation intent
as read-only. If excluded paths are omitted, state that no user-supplied
exclusions were provided and apply the repository's protected/default
exclusions. Do not infer a target when doing so would leave the repository root
ambiguous.

Use live command output and exact file paths; treat old reports, filenames,
counts, and prior summaries as leads only. Locate and report declared validation
commands, but do not run them during discovery.

## Output

Return:

1. Authority: repository root, applicable instructions, and conflicts.
2. State: branch, HEAD or explicit no-HEAD, dirty/untracked summary, baseline
   and prospective rollback boundary; include worktree state when relevant, or
   state why it was skipped.
3. Scope: included and excluded paths, expected touched paths, and risks.
4. Structure: relevant package roots, declared entrypoint/configuration files,
   tests, and declared validation surfaces. Mark runtime reachability and
   ownership as unknown unless active-path-inspection establishes them.
5. Unknowns: evidence still missing or contradictory.
6. Next: the permitted inspection or decision-gate action.

For each material claim include command, relevant output, exit code, and
interpretation.

## Stop conditions and authority

Stop on a missing or ambiguous target root, conflicting instructions, or
missing evidence needed for the next decision. Dirty state alone does not stop
read-only discovery: report it, separate known unrelated paths, and state that
any later mutation is blocked until the boundary is resolved or the user
approves proceeding. Mutation authority is none. A discovery result never
declares implementation or completion.

## Validation expectation

Validate that the reported root exists, instruction coverage is complete, live
repository state was checked, and included/excluded paths are explicit. A
valid discovery result proves context only, not runtime behavior.
