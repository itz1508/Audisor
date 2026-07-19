# Audisor Debug

Audisor has three local, read-only stages for Codex:

- `scan` is the visible deterministic capacity tool for Python, JSON, TOML,
  and YAML.
- `inspect` is the one canonical issue intake. It returns the original issue,
  ScanReport, Dossier, Handoff, safe snapshot, and immutable hash manifest.
- `validate` and `replay` verify the Gap Evaluation before a repair, then
  compare that original evidence with the current resolved repository.

```powershell
uv run --directory backend audisor scan D:\path\to\repo --json
uv run --directory backend audisor scan D:\path\to\repo --baseline HEAD --json
```

The three-stage verification flow uses JSON artifacts outside the inspected
repository so artifact writes cannot change the evidence being checked:

```powershell
uv run --directory backend audisor inspect inspection-request.json --json > inspection.json
uv run --directory backend audisor validate inspection.json evaluation.json --json > validation.json
# Codex performs the approved repair here.
uv run --directory backend audisor replay inspection.json validation.json --json
```

`inspection-request.json` contains `inspection_id`, `repository_root`,
original `issue`, and optional `baseline`. Replay is read-only: it re-runs the
scan, produces a redacted diff for the evaluated scope, and reports whether
each original finding is resolved, unresolved, or uncertain.

## Codex MCP bundle

Install the bundle, then explicitly register its local stdio server with Codex.
From this backend directory in a cloned repository:

```powershell
uv tool install .
```

Or, after publishing the distribution:

```powershell
uv tool install audisor-local
```

Then register the installed command:

```powershell
audisor install-codex
```

Start a new Codex session after registration. It exposes four native tools:
`audisor_scan`, `audisor_inspect`, `audisor_validate`, and `audisor_replay`.
They return the same deterministic artifacts as the CLI and never modify the
inspected repository. `install-codex` delegates registration to
`codex mcp add` with its package-owned Python executable and `-m audisor.cli
mcp`. This avoids collisions with an unrelated executable named `audisor`; it
is the only command that changes a Codex configuration, and it runs only when
explicitly invoked.

The scanner emits safe evidence only. It never returns a detected secret value.
Git drift is evaluated only when `--baseline` is supplied; otherwise the report
records baseline `uncertainty` rather than inventing drift.

```powershell
```
