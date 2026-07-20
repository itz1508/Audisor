---
name: audisor-smart-trace
description: Use Audisor's local read-only tools for a bounded coding or debugging request only after the original issue can be inspected. Run Trace when repair safety depends on callers, an entrypoint, overlapping ownership, or an uncertain affected scope. Do not use for read-only explanations, ordinary one-file edits with known callers, planning, or as a default hook.
---

# Audisor Smart Trace

## Purpose

Audisor supplies bounded evidence to Codex. It is not a planner, execution
agent, writer, hook, or substitute for Codex's repair judgment.

## Workflow

1. For an eligible repair, call `audisor_inspect` once with the original issue
   and repository root. Preserve the returned inspection artifact unchanged.
2. Call `audisor_trace` only when at least one is true: affected callers are
   unknown; an entrypoint may reach the code; the issue spans multiple files;
   a duplicate or overlap needs ownership evidence; or the scan has a relevant
   uncertainty. Do not trace a simple scoped edit with a known call path.
3. When the repair depends on semantic diagnosis, create an LLM Statement and
   call `audisor_normalize`. The Normalize Package contains Dossier, Handoff,
   and statement references only; it never contains snapshot content. Skip this
   step for a purely deterministic finding that already has sufficient evidence.
4. Classify every inspection finding as `valid`, `not_valid`, or `uncertainty`.
   Only a `valid` finding has a closure, included/excluded paths, measurable
   success criteria, and a focused validator.
5. Call `audisor_validate` before modifying source. If it blocks, do not repair.
6. Codex performs only the validated repair. Call `audisor_replay` only when a
   final review summary is useful; Replay is not an approval gate.

## Boundaries

- Do not send raw tasks to Trace.
- Do not call Trace after source changed from its inspection snapshot.
- Do not auto-fix secret signals, duplicates, overlaps, or Git drift from a
  scanner match alone.
- Do not claim runtime behavior from Replay unless the specified runtime
  validator was separately executed.
- If the Audisor MCP server is unavailable, say so; do not claim this review
  happened through another model or tool.
