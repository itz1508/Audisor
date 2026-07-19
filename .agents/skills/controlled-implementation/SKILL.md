---
name: controlled-implementation
description: |
  Use this skill only when the primary orchestrator has an explicit approved decision gate, exact writable target paths, rollback evidence, and focused validators for an Audisor change. Do not trigger for diagnosis, planning, plan review, setup/configuration, explanations, or implementation when scope, authority, rollback, or validation is unresolved. Do not use it to stage, commit, publish, deploy, or modify production authority outside the approved paths.
---

# Controlled Implementation

## Purpose

Apply an approved Audisor change inside an explicit path boundary while
preserving unrelated work and existing runtime authority.

## Preconditions and scope

Before editing, require:

- the user objective and accepted plan;
- independent gap review with no material blocker;
- exact writable paths and excluded paths;
- current branch, HEAD/no-HEAD, dirty state, and rollback path;
- active implementation and authority checks;
- focused validation commands and measurable success criteria.

Recheck state immediately before writing. Use apply_patch for local edits. Keep
the change narrow, do not create duplicate entrypoints, state roots, writers,
registries, runners, or deployment authorities, and do not edit outside the
approved paths.

## Exclusions and mutation authority

Preserve unrelated dirty and untracked work. Do not reset, clean, stash,
overwrite, stage, commit, push, publish, deploy, or perform destructive cleanup
unless separately authorized. Stop immediately if an unexpected path changes or
the diff exceeds scope. This skill is not permission to alter runtime behavior
without an approved target path.

## Required evidence and output

Record:

1. pre-change state and rollback location;
2. approved paths and intended ownership;
3. exact changed paths and diff;
4. focused commands, working directories, output excerpts, and exit codes;
5. preserved unrelated paths;
6. remaining gaps and stop condition.

Use Unverified_Execution_Claim when a required validator did not run.

## Post-change validation

Inspect the exact diff, compare target file lists/hashes when the repository has
no usable HEAD, run focused validation, and run broader regression checks only
when required by the accepted plan. A clean diff or passing unit test does not
independently prove entrypoint reachability, package inclusion, deployment, or
external compatibility.
