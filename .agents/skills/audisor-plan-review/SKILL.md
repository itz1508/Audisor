---
name: audisor-plan-review
description: Trigger the local Audisor MCP review for a completed implementation plan before coding. Use only when a valid plan document is detected — never for raw tasks, research, questions, or read-only work. Audisor returns additive companion artifacts; it never edits the plan or repository.
---

# Audisor Plan Review

## How it works

Audisor is a narrow plan qualifier, not a planner or executor. The host detects a **completed valid plan** by validating its structure against the plan-detection schema. When a valid plan is detected, the host calls `aflow_review` **exactly once** with `plan_digest="auto"`. Audisor computes the digest internally, reviews the immutable plan text, and returns a manifest with an outcome.

The host interprets the outcome at a **decision gate**:

| Outcome | Host action |
|---|---|
| `decision_required` | Stop before implementation. Request the stated human decision. |
| `supplement_ready` | Keep the original plan unchanged. Use companion artifacts as added implementation context. Proceed. |
| `no_material_gap` | Keep the original plan unchanged. No companion artifacts required. Proceed. |

Audisor never rewrites the original plan, never executes code, and never writes files.

## When to use

Use Audisor **only** when all of the following are true:

1. `source_kind` is `"plan"` (not `"task"`)
2. `expects_mutation` is `true`
3. `read_only` is `false`
4. `steps` contains at least one action

**Do not use Audisor for:**
- Raw user tasks without a drafted plan
- Research, explanations, or questions
- Read-only work (analysis, inspection, documentation reading)
- Work with no expected repository mutation

## Definitions

| Term | Definition |
|---|---|
| **plan** | A structured document with `plan_id`, ordered `steps`, and an `original_plan` text field. The source of truth for implementation. |
| **task** | A raw user request. May or may not include a plan. Audisor never receives raw tasks. |
| **aflow_review** | The MCP tool that reviews an immutable plan and returns additive companion artifacts. |
| **manifest** | The review result containing `outcome`, `plan_id`, `artifacts`, and optionally `plan_digest`. |
| **outcome** | One of `no_material_gap`, `supplement_ready`, `decision_required`. |
| **plan_digest="auto"** | Instructs Audisor to compute the SHA-256 digest of `original_plan` internally. Collapses "submit plan" and "call aflow_review" into one step. |
| **decision gate** | The host-side interpretation of the review outcome that determines whether to proceed, block, or request human input. |
| **companion artifacts** | Additive documents returned by Audisor (gap review, evaluation, validation fixtures, validation tests, plan update). Never modify the original plan. |
| **source_kind** | `"plan"` for completed plans; `"task"` for raw user requests. Only `"plan"` triggers automatic review. |
| **expects_mutation** | Boolean. `true` when the plan expects to write files, change configuration, or otherwise mutate the repository. |
| **read_only** | Boolean. `false` for implementation work; `true` for inspection or research. |

## Plan detection schema

A valid plan document must satisfy this schema. The host validates structure only — no hashing, no task-kind classification.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://theoneshot.dev/schemas/aflow/v1/plan-detection.schema.json",
  "title": "Audisor Plan Detection",
  "description": "Defines a completed valid plan that automatically triggers Audisor review. No hashing or task-kind classification is used for detection. The host validates plan structure only.",
  "type": "object",
  "additionalProperties": true,
  "required": ["plan_id", "source_kind", "expects_mutation", "read_only", "steps", "original_plan"],
  "properties": {
    "plan_id": {
      "type": "string",
      "minLength": 1,
      "description": "Stable, non-empty identifier for this plan."
    },
    "source_kind": {
      "enum": ["plan"],
      "description": "Must be 'plan'. Raw tasks use source_kind='task' and do NOT trigger automatic Audisor review."
    },
    "expects_mutation": {
      "type": "boolean",
      "description": "Must be true. Indicates the plan expects to mutate the repository."
    },
    "read_only": {
      "type": "boolean",
      "description": "Must be false. Read-only work never triggers Audisor review."
    },
    "steps": {
      "type": "array",
      "minItems": 1,
      "description": "Ordered list of planned actions. Must contain at least one step.",
      "items": {
        "type": "object",
        "required": ["action_id", "objective"],
        "properties": {
          "action_id": { "type": "string", "minLength": 1 },
          "objective": { "type": "string", "minLength": 1 },
          "target_paths": { "type": "array", "items": { "type": "string" } },
          "evidence_gates": { "type": "array", "items": { "type": "string" } }
        }
      }
    },
    "original_plan": {
      "type": "string",
      "minLength": 1,
      "description": "The full immutable plan text passed verbatim to aflow_review."
    },
    "evidence_gates": {
      "type": "array",
      "description": "Optional validation checkpoints.",
      "items": {
        "type": "object",
        "required": ["gate_id", "criterion"],
        "properties": {
          "gate_id": { "type": "string", "minLength": 1 },
          "criterion": { "type": "string", "minLength": 1 }
        }
      }
    }
  },
  "allOf": [
    {
      "if": {
        "properties": {
          "source_kind": { "const": "plan" },
          "expects_mutation": { "const": true },
          "read_only": { "const": false }
        }
      },
      "then": {
        "properties": {
          "trigger_action": { "enum": ["auto_review", "direct_review"] }
        }
      }
    },
    {
      "if": {
        "anyOf": [
          { "properties": { "source_kind": { "const": "task" } } },
          { "properties": { "expects_mutation": { "const": false } } },
          { "properties": { "read_only": { "const": true } } }
        ]
      },
      "then": {
        "properties": {
          "trigger_action": { "const": "skip" }
        }
      }
    }
  ]
}
```

## Tool parameters

Call `aflow_review` exactly once per plan.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `original_plan` | `string` | Yes | The unchanged plan text. Never substitute raw task text. |
| `plan_id` | `string` | Yes | A stable, non-empty identifier. |
| `plan_digest` | `string` | No | `"auto"` to compute internally, or a 64-char hex SHA-256. Defaults to `"auto"`. |

## Returns and interpretation

The tool returns:

```json
{
  "manifest": {
    "schema_version": "1.0.0",
    "plan_id": "<plan_id>",
    "outcome": "<outcome>",
    "artifacts": ["gap-review.json", "gap-fulfillment.md", "evaluation.json", "validation-fixtures.json", "validation-tests.json", "plan-update.md"],
    "plan_digest": "<sha256>"
  },
  "artifacts": {
    "manifest.json": "<canonical_json>",
    "gap-review.json": "<findings_and_decisions>",
    "gap-fulfillment.md": "<markdown>",
    "evaluation.json": "<success_criteria>",
    "validation-fixtures.json": "<fixtures>",
    "validation-tests.json": "<tests>",
    "plan-update.md": "<markdown>"
  }
}
```

### Outcome interpretation

- **`no_material_gap`**: The plan is clean. Proceed with implementation using the original plan unchanged. Companion artifacts are optional context.
- **`supplement_ready`**: The plan is clean but Audisor found missing context (success criteria, validation, fixtures). Proceed with the original plan unchanged. Apply companion artifacts as additive implementation context.
- **`decision_required`**: The plan contains unresolved design decisions. **Stop.** Request human resolution before implementation. Do not proceed.

## Examples

### Example 1: Valid plan document that triggers review

```json
{
  "plan_id": "feature-auth-001",
  "source_kind": "plan",
  "expects_mutation": true,
  "read_only": false,
  "steps": [
    {
      "action_id": "step-1",
      "objective": "Add JWT middleware to API gateway",
      "target_paths": ["src/middleware/auth.py"],
      "evidence_gates": ["test-jwt-validation"]
    },
    {
      "action_id": "step-2",
      "objective": "Update user model with token fields",
      "target_paths": ["src/models/user.py"]
    }
  ],
  "original_plan": "## Authentication Feature\n\n1. Add JWT middleware to API gateway (src/middleware/auth.py)\n2. Update user model with token fields (src/models/user.py)\n3. Add tests for token validation\n\nSuccess criteria: All existing tests pass; new auth tests cover login/logout flows.",
  "evidence_gates": [
    { "gate_id": "test-jwt-validation", "criterion": "JWT tokens are validated in middleware tests" }
  ]
}
```

### Example 2: aflow_review call

```json
{
  "original_plan": "## Authentication Feature\n\n1. Add JWT middleware...\n2. Update user model...\n3. Add tests...",
  "plan_id": "feature-auth-001",
  "plan_digest": "auto"
}
```

### Example 3: no_material_gap response → proceed

```json
{
  "manifest": {
    "outcome": "no_material_gap",
    "plan_id": "feature-auth-001",
    "artifacts": ["gap-review.json", "gap-fulfillment.md", "evaluation.json", "validation-fixtures.json", "validation-tests.json", "plan-update.md"]
  }
}
```

**Host action**: Keep original plan unchanged. Proceed with implementation.

### Example 4: supplement_ready response → proceed with context

```json
{
  "manifest": {
    "outcome": "supplement_ready",
    "plan_id": "feature-auth-001",
    "artifacts": ["gap-review.json", "gap-fulfillment.md", "evaluation.json", "validation-fixtures.json", "validation-tests.json", "plan-update.md"]
  },
  "artifacts": {
    "gap-review.json": "{\"findings\":[{\"id\":\"validation\",\"reason\":\"Add a validation specification as a companion record.\"}]}"
  }
}
```

**Host action**: Keep original plan unchanged. Use the validation specification from companion artifacts as added context. Proceed with implementation.

### Example 5: decision_required response → stop

```json
{
  "manifest": {
    "outcome": "decision_required",
    "plan_id": "feature-auth-001",
    "artifacts": ["gap-review.json", "gap-fulfillment.md", "evaluation.json", "validation-fixtures.json", "validation-tests.json", "plan-update.md", "decision-required.json"]
  },
  "artifacts": {
    "decision-required.json": "{\"decisions\":[{\"id\":\"design-decision-required\",\"reason\":\"The plan explicitly requires a design decision. Audisor must not invent that decision.\"}]}"
  }
}
```

**Host action**: Stop before implementation. Present the design decision to the human and request resolution.

## Automatic trigger

For any agent (not only Codex), when a completed valid plan is detected, the Audisor review triggers **automatically**. The host:

1. Validates the plan document against the plan-detection schema
2. Calls `aflow_review` with `plan_digest="auto"`
3. Interprets the outcome at the decision gate
4. Returns the decision to the agent workflow

The automatic trigger works for **any agent**. The bridge accepts an `agent_identity` parameter that records which agent owns the resulting lock. When omitted, it defaults to `"primary_codex"` for backward compatibility.

## Error handling

If the MCP tool is unavailable, report the missing local Audisor configuration. Do not replace Audisor with another agent or cloud model.

If `aflow_review` returns an error, the bridge returns `decision: "blocked"` with the error reason.

If the review outcome is unexpected (not `no_material_gap`, `supplement_ready`, or `decision_required`), the bridge returns `decision: "blocked"`.