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
3. Classify every inspection finding as `valid`, `not_valid`, or `uncertainty`.
   Only a `valid` finding has a closure, included/excluded paths, measurable
   success criteria, and a focused validator.
4. Call `audisor_validate` before modifying source. If it blocks, do not repair.
5. Codex performs only the validated repair. Then call `audisor_replay` to
   connect original evidence, changed scope, current scan, and resolution.

## Boundaries

- Do not send raw tasks to Trace.
- Do not call Trace after source changed from its inspection snapshot.
- Do not auto-fix secret signals, duplicates, overlaps, or Git drift from a
  scanner match alone.
- Do not claim runtime behavior from Replay unless the specified runtime
  validator was separately executed.
- If the Audisor MCP server is unavailable, say so; do not claim this review
  happened through another model or tool.
