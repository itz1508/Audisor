---
name: active-path-inspection
description: |
  Use this read-only skill when the task requires tracing Audisor's active implementation through definitions, imports, callers, canonical entrypoints,packaging, schemas, tests, or deployment boundaries. Do not trigger for a repository orientation scan (use repository-discovery), explanations, setup/configuration, plan review, requirement scoring, validator sufficiency review, or implementation/debugging by itself.
---

# Active Path Inspection

## Purpose

Determine which Audisor component actually owns a behavior. A matching filename
or text search is not activation evidence.

## Scope and exclusions

- Start from the canonical backend package and public launcher defined by the
  applicable instructions.
- Trace definitions, imports, callers, entrypoints, package inclusion,
  schemas/interfaces, tests, and declared deployment boundaries.
- Classify findings as active, generated, historical, advisory, compatibility,
  experimental, test-only, or residue when evidence supports the label.
- Do not edit source, tests, schemas, configuration, or evidence; do not infer
  runtime behavior from source inspection alone.
- Do not redesign the backend phase order or create a parallel authority.

## Required inputs and evidence

Require a behavior, symbol, path, or requirement to trace. Use rg, file
inspection, import/caller searches, package metadata, entrypoint checks, and
focused tests or commands only when they are safe and approved. Record exact
paths and the call sequence supporting each ownership claim.

## Output

Return:

- Question and inspected scope;
- Active path as definition -> import -> caller -> entrypoint -> package/test
  evidence;
- Ownership classification for duplicate or dormant candidates;
- Boundary checks for schemas, writers, mutation authorities, and deployment;
- Contradictions or unknowns;
- Next evidence step or decision gate.

Separate observed evidence, interpretation, unresolved questions, and next
action. State I don't know. when the active owner cannot be established.

## Stop conditions and authority

Stop when the canonical entrypoint, package inclusion, or caller chain cannot
be established, or when a proposed change would promote a new authority path.
Mutation authority is none. This skill cannot declare a fix complete.

## Validation expectation

At minimum, reconcile text matches to imports/callers and confirm the claimed
entrypoint and package surface. Tests are supporting evidence, not proof of
activation, deployment, or external compatibility.
