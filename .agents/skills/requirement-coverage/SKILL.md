---
name: requirement-coverage
description: |
  Use this read-only skill when explicit user requirements, a specification,
  an acceptance list, or an evidence packet must be reconciled against current
  Audisor implementation and artifacts. Do not trigger for creating a plan,
  reviewing a draft plan (use plan-gap-review), testing alone, validator design
  alone (use validation-gap-review), explanations, or implementation work.
---

# Requirement Coverage

## Purpose

Judge whether each requested requirement is represented by current inspected
implementation and evidence. Coverage is separate from test success.

## Scope and exclusions

- Normalize the user requirements into individually testable statements.
- Map every statement to exact target paths, active call paths, schemas,
  commands, tests, or artifacts.
- Classify each item as pass, fail, partial, unverified, or not_applicable only
  with supporting evidence.
- Do not modify implementation, tests, schemas, reports, or runtime state.
- Do not infer hidden work, hidden runs, or completion from aggregate counts.

## Required inputs and evidence

Require the authoritative requirement text and the current target scope. Read
applicable instructions first. Use current files and executed artifacts; when
execution proof is absent, use Unverified_Execution_Claim.

## Output

Return a requirement matrix with:

| Requirement | Target surface | Evidence checked | Verdict | Gap/next action |
|---|---|---|---|---|

Then report duplicate authority risks, exclusions, unsupported assumptions,
missing evidence, and whether any completion claim is blocked.

## Stop conditions and authority

Stop when the requirement source is ambiguous, a mapping would require
redesign outside scope, or an evidence claim cannot be reconciled to a current
artifact. Mutation authority is none. This skill reports coverage; it does not
authorize changes or declare production readiness.

## Validation expectation

Check both positive and negative cases, including requested-but-not-implemented
and implemented-but-unverified states. A passing test without requirement
coverage remains incomplete.
