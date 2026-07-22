# Audisor

Audisor is a local, read-only evidence tool for Codex. It captures an issue's
original state, maps static parents when useful, validates a complete repair
evaluation, and replays the resolved repository without turning itself into a
second coding agent.

```text
Issue -> Inspect -> optional Trace -> optional Normalize -> Validate -> Codex repair -> optional Replay
```

The six tools are `audisor_scan`, `audisor_inspect`, `audisor_trace`,
`audisor_normalize`, `audisor_validate`, and `audisor_replay`. Codex remains
the only writer.

## Normalize contract

`audisor normalize inspection.json llm-statement.json --json` creates the
optional semantic Normalize Package from Dossier, Handoff, and an LLM
Statement. It references an Inspection ID, Inspection hash, and finding IDs
only. It never embeds snapshot content or Replay output, and it does not create
an apply/skip approval workflow.

## Quick start

Native installation (Windows, macOS, Linux) uses the published package:

```powershell
./scripts/install.ps1
```

```sh
./scripts/install.sh
```

Both installers register the local stdio MCP server with Codex. Start a new
Codex session after installation. To run the safe end-to-end judge fixture:

```powershell
python ./scripts/run_demo.py --output-root ./demo-output
```

See [JUDGE_QUICKSTART.md](JUDGE_QUICKSTART.md) for native, Docker, and Codex
plugin installation. Docker uses the same core and accepts a repository only
through an explicit read-only `/workspace` mount. The submitted public Docker
image is:

```text
ghcr.io/itz1508/theoneshot-audisor-agent:submission-20260721
```

It was verified as anonymously pullable after `docker logout ghcr.io`.

## Boundaries

- Audisor does not patch, apply, commit, publish, or deploy source changes.
- Scanner matches are evidence, not automatic repair instructions.
- Trace is skill-driven for ambiguous or risky repairs; it is not a default
  hook and is not needed for ordinary scoped edits.
- Snapshots, diffs, and image previews redact secret-shaped values and bound
  image content before it leaves the inspected repository.

Licensed under [Apache-2.0](LICENSE).

The backend migration preserves the existing phase behavior and intentionally does not add an HTTP API, conversation memory, or automatic duplicate cleanup.
