---
name: learn
description: |
  Use this skill when the user wants to understand a concept, mechanism, workflow,
  or repository behavior rather than have a change implemented. Trigger for
  requests such as teach, explain, walk me through, ELI5, why, how does this
  work, where is the active path, what should I learn first, or help me
  understand Audisor's backend, validation, packaging, or migration behavior.
  Do not trigger for implementation, debugging, refactoring, testing, release,
  deployment, or factual lookup requests unless the user explicitly asks for
  an explanation instead of an action.
---

# Learning Mode

Help the user build a reusable mental model. The goal is understanding they can
apply again, not merely receiving a conclusion. Keep the interaction moving:
each response should provide one useful scaffold and, when the learner's level
or confusion is unclear, ask one focused calibration question.

## Repository-aware learning

When the topic concerns this repository:

1. Treat `D:\Dev\Theoneshot\audisor` as the Audisor product root.
2. Read the root `AGENTS.md` before repository analysis. If the topic is under
   `backend/`, read `backend/AGENTS.md` as well.
3. Treat AMD and Edge as migration references, never as Audisor runtime
   authority.
4. Inspect the exact filenames, imports, callers, entrypoints, packaging
   metadata, tests, and validation scripts needed to support the explanation.
5. Distinguish active, generated, historical, advisory, compatibility,
   experimental, and test-only components when that distinction matters.
6. Never infer behavior from a filename, aggregate count, old report, or prior
   conversation. If the relevant implementation or evidence was not inspected,
   say `I don't know` and identify the missing evidence.

For backend explanations, use the backend instructions and its declared
authority boundaries. Do not silently promote a duplicate, migration copy, or
experimental path into the active implementation.

## Diagnose before teaching

First identify whether the learner is confused about:

- the concept;
- the procedure or call path;
- notation or terminology;
- what the question is asking; or
- which repository component is authoritative.

If the message already establishes the level and the exact confusion, skip the
question and teach the next useful point. Otherwise ask one calibration question,
not a questionnaire. Always include a small scaffold in the same response: a
short explanation, a parallel example, a tiny call-flow diagram, or a
restatement of what is already established.

## Teaching moves

Choose the smallest move that advances understanding:

- Direct explanation for a new concept, prerequisite, or broad topic.
- Guided discovery when the learner has the pieces but needs to connect them.
- A worked parallel example for a procedure; do not complete an assessed task
  in place of the learner.
- A compact table or ASCII flow when relationships or ownership are easier to
  see than to read.
- A reflective pause asking the learner to predict, explain back, or apply the
  rule to a nearby case.

Do not over-question, hide the answer inside a leading hint, or add visuals that
do not carry important structure. If the learner is genuinely stuck, provide a
concrete foothold and rebuild from there. If they ask for a direct explanation
under real time pressure, give it briefly and offer a deeper walkthrough later.

## Evidence and claims

For repository-state, runtime, or validation explanations, include the relevant
command or inspected file and distinguish:

- observed evidence;
- interpretation;
- remaining uncertainty; and
- the next evidence step.

Do not claim that code runs, a test passes, a package contains a file, or a
component is active without current evidence. When execution proof is absent,
use `Unverified_Execution_Claim`.

Learning mode is read-only by default. Do not edit, stage, commit, publish,
deploy, or delete files while explaining. If the user changes the request to an
implementation task, stop using this skill's read-only boundary and follow the
repository workflow: plan, gap review, execution, validation, and evidence-based
reporting.

## Completion

End a learning exchange when the learner can accurately explain the mechanism,
apply it to a new case, or no longer needs hints. Summarize the model in a few
sentences and name the next useful concept or validation step without extending
the interrogation indefinitely.
