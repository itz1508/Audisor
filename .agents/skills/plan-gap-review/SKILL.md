---
name: plan-gap-review
description: |
  Use this read-only skill when an existing Audisor draft plan or design needs
  an independent gap review before execution. Trigger only when a plan is
  already present. Do not trigger to create a plan, perform setup/configuration,
  explain the workflow, implement changes, or validate
  runtime behavior.
---

# Plan Gap Review

## Purpose

Challenge a draft plan independently without silently redesigning the requested
solution. The primary orchestrator retains interpretation, authority
resolution, decision-gate, and completion authority.

## Scope and exclusions

Review the plan against the user objective, applicable Audisor instructions,
live repository state, active implementation, target/excluded paths,
dependencies, authority boundaries, rollback, and proposed validators.

Do not edit the plan or repository, run implementation commands, approve the
plan, expand scope, or invent missing evidence. Setup/configuration requests
and conceptual questions are outside this skill's scope.

## Required inputs and evidence

Require the draft plan, approved scope, repository-state evidence, source and
target paths, authority chain, dependencies, rollback approach, and validation
commands. Recheck only the read-only evidence needed to test plan assumptions.

## Output

For every gap return:

- affected plan step;
- missing, contradictory, vague, or unsupported detail;
- why it matters;
- concrete correction that preserves user intent;
- blocks_execution: yes|no.

Also return requirement coverage, ownership checks, authority/scope risks,
positive and negative validation cases, measurable success criteria, stop
conditions, and any user decision required.

## Stop conditions and authority

Stop with Blocked when a material authority conflict, destructive action,
missing prerequisite, unavailable rollback, or unprovable validator remains.
Mutation authority is none; the reviewer cannot approve its own recommendation.

## Validation expectation

The reviewed plan is executable only when all requirements are represented,
steps are specific and ordered, ownership and authority are known or explicitly
blocked, rollback is possible, and validation can distinguish completion from
partial or unverified work.
