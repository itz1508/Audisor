---
name: focused-validation
description: |
  Use this skill after an approved Audisor change when the task is to execute
  the smallest safe validators for the changed path and report their evidence.
  Do not trigger for designing a validator (use validation-gap-review), initial
  discovery, plan review, explanations, setup/configuration, or implementation.
---

# Focused Validation

## Purpose

Prove the changed Audisor behavior through the active production path and
nearby contracts before expanding to broader regression checks.

## Scope and exclusions

- Read applicable AGENTS.md files and the accepted success definition.
- Inspect the exact diff and identify the canonical entrypoint, package surface,
  schemas, tests, and focused validators affected by the change.
- Run only approved, bounded commands with controlled output roots.
- Do not edit source, tests, schemas, configuration, or evidence; do not repair
  failures silently; do not stage, commit, publish, deploy, or release.

## Required evidence

For every command record the exact command, working directory, relevant output,
exit code, touched paths, and interpretation. Include positive and negative
cases and distinguish compile/source, unit, entrypoint, package, runtime, and
external-service proof. Missing execution proof is
Unverified_Execution_Claim.

## Output and stop conditions

Return:

- changed-path and active-entrypoint check;
- focused validator results;
- failure or negative-case results;
- requirement coverage status;
- unverified or blocked claims;
- next broader validator, if required;
- final stop condition.

Stop when a command mutates an unapproved path, the active path cannot be
reached, a required dependency or environment gate is missing, or validation
cannot distinguish requested-but-not-implemented from passing. A passing test
does not authorize a completion claim by itself.
