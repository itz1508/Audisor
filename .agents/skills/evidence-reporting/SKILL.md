---
name: evidence-reporting
description: |
  Use this read-only skill after approved inspection or validation when the
  user needs a final Audisor evidence report with exact paths, commands,
  outputs, exit codes, interpretations, gaps, and stop condition. Do not
  trigger for initial discovery, implementation, ordinary testing, plan
  creation/review, or conceptual explanations.
---

# Evidence Reporting

## Purpose

Assemble a bounded report from evidence inspected during the current task. It
does not create proof that was not executed or inspected.

## Scope and exclusions

- Report only current files, diffs, artifacts, transcripts, and command output.
- Include repository path, branch, HEAD or no-HEAD, dirty state, touched paths,
  excluded paths, rollback boundary, and authority risks when relevant.
- Preserve the distinction between passed, failed, blocked, and
  Unverified_Execution_Claim.
- Do not edit source or reports unless a separately authorized output path is
  explicitly in scope; do not stage, commit, publish, deploy, or release.
- Do not repeat stale reports as current evidence.

## Required inputs and evidence

Require the user objective, scope, inspected paths, exact commands, relevant
output excerpts, exit codes, validation results, and unresolved findings.

## Output

Use:

Changed:
Commands_Run:
Result:
Evidence:
Remaining_Gaps:
Rollback:
Stop_Condition:

Connect every material claim to a path or command. State what was required,
what was checked, what supports the verdict, and what was missing or
contradicted.

## Stop conditions and authority

Stop with Blocked or Unverified_Execution_Claim when current proof is missing,
conflicting, or outside scope. Mutation authority is none unless a separate
approved report path is provided; reporting never promotes an artifact, writer,
runner, or deployment path to authority.

## Validation expectation

Check that the report is complete, current, reproducible from its commands,
scope-bounded, and honest about failures and unverified areas. A polished
summary without supporting evidence is not a passing report.
