---
name: init
description: |
  Use this skill when the user asks to initialize or review Audisor repository
  instructions, project-local skills, backend workflow setup, or agent
  configuration. Trigger for requests such as initialize the repo, set up
  AGENTS.md, create or review a skill, map backend tools, explain the workflow,
  or find setup gaps. Do not trigger for ordinary implementation, debugging,
  testing, packaging, release, deployment, or migration work unless setup or
  workflow understanding is the requested subject.
---

# Audisor Init and Workflow Setup

This skill explains and improves the repository workflow. It is not a blank
command runner. Every tool must have a workflow purpose, a known input, an
expected evidence artifact, a pass/fail interpretation, and a next step.

The supported authority chain is:

```text
AGENTS.md -> .agents/skills/<name>/SKILL.md -> backend workflow tools -> evidence
```

The required operating loop is:

```text
authority -> orient -> plan -> independent gap review -> user decision
-> bounded execution -> phase validation -> evidence report
```

## Supported setup

Only these repository surfaces are supported:

- `AGENTS.md` — authority, scope, workflow, validation, and stop rules;
- nested `AGENTS.md` — narrower rules for a target directory;
- `.agents/skills/<name>/SKILL.md` — repeatable workflows that explain or
  perform approved work;
- backend code, tests, artifacts, and reports — implementation and evidence.

Do not create a competing instruction root, a second skill root, a second
runtime, a second state root, or an unrelated automation framework. Do not
replace a repository rule with a copied external rule. Preserve the AMD working
tree and keep AMD/Edge as migration references only.

## 1. Authority and orientation

Before exploring or changing anything:

1. Treat `D:\Dev\Theoneshot\audisor` as the Audisor product root.
2. Read root `AGENTS.md`.
3. If the target is under `backend/`, read `backend/AGENTS.md`.
4. Identify the user's objective, interpretation, target paths, excluded paths,
   and whether mutation is authorized.
5. Run `git status --short --branch`, inspect `HEAD`, and run
   `git worktree list` when worktree context matters.

The orientation result must name the active authority, current implementation,
known dirty or unrelated paths, rollback boundary, and missing evidence. A
filename, directory name, report, or previous answer is not proof of runtime
ownership.

## 2. Tool-purpose map

Use tools as workflow moves, not as disconnected commands:

| Workflow move | Tool | What it establishes | What comes next |
|---|---|---|---|
| Orient | `Get-Content`, `rg`, `rg --files` | Instructions, paths, imports, callers, schemas, and tests | Active ownership statement |
| Scope | `git status`, `git worktree list` | Branch, `HEAD`, dirty files, worktrees, rollback risk | Approved target boundary |
| Plan | `update_plan` | Ordered actions, dependencies, validation, success criteria | Independent review |
| Gap review | `multi_agent_v1__spawn_agent` with `agent_type="explorer"` and `fork_context=true` | Read-only challenge to assumptions and missing evidence | Revised plan or `Blocked` |
| Decision | User approval | Authority to mutate named paths | Bounded execution |
| Mutation | `apply_patch` | Approved setup-file change | Exact diff inspection |
| Verify | Backend CLI, tests, compile, package, pipeline | Current behavior and artifact evidence | Report or stop |

Never run a command only to produce output. Before each command, state its
workflow stage and expected result; after it, state the observed result,
interpretation, and next action.

## 3. Plan and independent gap review

Create a task-specific plan containing:

- objective and interpretation;
- target and excluded paths;
- active implementation and authority chain;
- branch, `HEAD`, dirty/unrelated paths, and rollback approach;
- ordered actions and dependencies;
- exact validation commands;
- measurable success criteria and stop conditions.

Review the plan separately before execution. Check that:

- every user requirement is represented;
- no step creates duplicate authority or expands scope;
- active ownership is supported by exact call-path evidence;
- every skill has a discoverable path and precise trigger/non-trigger rules;
- backend tools correspond to a workflow stage and expected artifact;
- dirty-state and rollback risks are addressed;
- validation distinguishes completion from partial completion.

For every gap, state the affected step, missing evidence, consequence,
correction, and whether it blocks execution. If a material gap remains, stop as
`Blocked` and request the evidence or approval needed to continue.

Use `multi_agent_v1__wait_agent` only when an explorer result is needed. Do not
use parallel write agents for setup or workflow changes.

## 4. Audisor backend workflow

The backend is a nine-phase evidence workflow, not nine unrelated commands:

```text
snapshot
  -> scan
  -> analysis_classification
  -> statement_output
  -> gap_evaluation
  -> simulation_environment
  -> inspection
  -> final_result
  -> cleanup
```

Each phase consumes the prior phase's artifact and must produce evidence for the
next phase. Explain the current phase before invoking its command.

| Phase | Purpose | Expected evidence | Stop or next route |
|---|---|---|---|
| `snapshot` | Capture bounded filesystem state | Snapshot artifact and source boundary | Continue to scan or fail on invalid target/boundary |
| `scan` | Analyze captured files | Scan artifact tied to snapshot | Continue to classification |
| `analysis_classification` | Normalize, classify, and group findings | Classification artifact and evidence references | Continue to statements |
| `statement_output` | Convert analysis into handoff statements | Statement artifact with references | Continue to gap evaluation |
| `gap_evaluation` | Check whether the plan/evidence is admissible | Executed gap checks and decision artifact | Correct and retry, or stop for operator action |
| `simulation_environment` | Prepare isolated, self-contained proof | Simulation readiness and execution evidence | Continue only when simulation is ready |
| `inspection` | Verify existing execution evidence | Inspection artifact with propagated evidence | Continue to final result or record failure |
| `final_result` | Lock and summarize verified evidence | Final-result artifact based on prior evidence | Continue only if cleanup is requested |
| `cleanup` | Apply approved retention policy | Cleanup evidence and deletion result | Default is denied, unconfirmed, or dry-run |

The defined lifecycle matters:

- invalid gap evaluation can require correction or terminate at
  `operator_action_required`;
- simulation, inspection, and final-result phases must not synthesize proof;
- cleanup requires explicit current authorization and an approved operator
  package before destructive action;
- a terminal status is meaningful only when its required artifact and evidence
  exist.

Do not skip from a command to a success claim. Show the artifact, status, exit
code, and transition that justify the next phase.

## 5. Backend tool reference by workflow stage

Run backend commands from `D:\Dev\Theoneshot\audisor\backend`:

| Stage | Command | Use and evidence |
|---|---|---|
| Environment | `uv sync --extra dev` | Establish the declared Python environment; not test proof. |
| Environment | `npm install` | Establish the declared Node environment; not package proof. |
| Contract check | `uv run python -m audisor_backend --help` | Verify the Python entrypoint is reachable. |
| Contract check | `audisor --help` and `audisor --version` | Verify the public launcher surface. |
| Regression | `uv run pytest tests -q` | Verify current backend behavior; record collection and exit code. |
| Compilation | `uv run python -m compileall -q audisor_backend` | Verify modules compile; not runtime proof. |
| Packaging | `uv build --out-dir <approved-output>` | Verify wheel/sdist artifacts in a bounded output. |
| Package boundary | `npm pack --dry-run` | Verify npm inclusion without publishing. |
| Lifecycle | `audisor pipeline <target> --output-root <external-output>` | Exercise the canonical phase workflow with external output. |

For a full backend validation, add clean wheel installation, packaged-module
imports, Python and public CLI surfaces, valid and invalid pipeline cases, and
current artifact/report inspection. Record each command, working directory,
relevant output, exit code, and phase interpretation in the approved report
path, including `backend/migration/validation-report.json` when backend
validation is being updated.

Never perform destructive cleanup from setup alone. Require an explicit
approved operator package, current authorization evidence, bounded output roots,
and recorded deletion results. Without those conditions, use dry-run or stop.

## 6. Evidence and claim discipline

For every material conclusion, separate:

- **Observed** — exact file, artifact, command output, or exit code;
- **Interpreted** — what that evidence means in the workflow;
- **Unresolved** — what remains unknown or unvalidated;
- **Next** — the permitted next stage or required decision.

Treat `backend/migration/validation-report.json` as a claim set to verify. Do
not invent hashes, pass counts, phase success, package contents, runtime
behavior, or cleanup results. Use `Unverified_Execution_Claim` when execution
proof is absent.

## 7. Bounded setup execution

After explicit user approval:

1. Recheck the exact target paths and dirty state.
2. Preserve unrelated changes and untracked files.
3. Do not overwrite an existing skill; make an additive edit or use a new name.
4. Keep each skill focused on a workflow, its trigger, evidence, and stop rule.
5. Use `apply_patch` for local edits.
6. Do not change backend phase order, schemas, artifact names, validators,
   cleanup authorization, or public CLI surfaces during setup.

If a skill refers to backend behavior, reference the current instructions and
phase/tools rather than copying a second contradictory implementation guide.

## 8. Validation and report

After mutation, inspect the exact diff and verify:

- only approved paths changed;
- the file is exactly `SKILL.md` under `.agents/skills/<name>/`;
- frontmatter name and directory name agree;
- the trigger describes both purpose and activation conditions;
- non-triggers prevent ordinary coding work from invoking setup;
- every backend reference points to a current path and command;
- each command has a workflow purpose and evidence interpretation;
- no runtime authority, schema, phase order, or cleanup boundary changed;
- focused structural/discovery checks exit successfully.

Do not rerun the complete backend suite for a skill-only change unless the
approved plan requires runtime validation. A skill discovery pass proves
discoverability, not backend runtime behavior.

Report exactly:

```text
Changed:
Commands_Run:
Result:
Evidence:
Stop_Condition:
```

`Result` must distinguish `Passed`, `Failed`, `Blocked`, and
`Unverified_Execution_Claim`. Stop when the approved setup is validated, when a
required decision or evidence is missing, or when the next step would expand
authority or scope.

## Success definition

Initialization succeeds when the approved `AGENTS.md` and/or
`.agents/skills/` paths are discoverable, the skill explains the workflow rather
than merely listing commands, every tool reference has a purpose and evidence
route, backend phase transitions and safety boundaries are preserved, unrelated
work is untouched, and the report contains current commands, exit codes, and
interpretation.