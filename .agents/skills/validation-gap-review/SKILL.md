---
name: validation-gap-review
description: |
  Use this read-only skill when the task is to assess whether proposed or
  executed Audisor validators prove requirement coverage, active-path behavior,
  packaging, runtime behavior, or evidence integrity. Do not trigger for a
  draft-plan review (use plan-gap-review), ordinary test execution, explanations,
  setup/configuration, or implementation.
---

# Validation Gap Review

## Purpose

Determine whether the available validators can prove the requested outcome,
including completeness, negative cases, and authority preservation. Test
success is only one input.

## Scope and exclusions

- Inspect the requested requirements, active production path, validators, test
  layout, packaging, entrypoints, artifacts, and current run evidence.
- Check positive, negative, missing-implementation, failure, and
  unverified-execution cases.
- Distinguish source/compile proof, unit proof, entrypoint proof, package proof,
  runtime proof, external-service proof, and release/deployment proof.
- Run only approved read-only or bounded validation commands; do not edit,
  delete, publish, deploy, or silently repair outputs.

## Required inputs and evidence

Require the success definition, validator list or commands, target scope, and
current evidence. Record exact command, working directory, output excerpt,
exit code, touched paths, and interpretation. Missing execution proof is
Unverified_Execution_Claim.

## Output

Return a validator sufficiency matrix:

| Requirement | Validator/evidence | What it proves | What it cannot prove | Verdict |
|---|---|---|---|---|

Then list missing positive/negative cases, authority or scope risks, blocked
claims, and the smallest permitted next validation.

## Stop conditions and authority

Stop when a required validator is unavailable, would mutate an unapproved
surface, or cannot distinguish requested-but-not-implemented from passing.
Mutation authority is none. Never declare completion from a green test alone.

## Validation expectation

The review passes only when requirement completeness, active-path reachability,
applicable package/runtime boundaries, failure behavior, and evidence identity
are covered or explicitly marked unverified/blocked.
