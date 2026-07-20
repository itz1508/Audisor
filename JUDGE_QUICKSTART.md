# Audisor judge quickstart

Audisor is a local, read-only MCP tool. It gives Codex immutable issue evidence,
optional semantic Normalize context, and replay proof; it never writes the
repository being inspected.

## Native path

Prerequisites: Python 3.11+, [uv](https://docs.astral.sh/uv/), and Codex.

```powershell
./scripts/install.ps1
python ./scripts/run_demo.py --output-root ./demo-output
```

```sh
chmod +x ./scripts/install.sh
./scripts/install.sh
python ./scripts/run_demo.py --output-root ./demo-output
```

The installer runs `audisor install-codex`, which adds the package-owned stdio
server to Codex. Start a new Codex session before testing the tools.

## Docker path

Prerequisite: Docker Engine. Build locally before registry publication:

```sh
docker build -f docker/Dockerfile -t audisor:0.2.0 .
docker run --rm --read-only --user 10001:10001 \
  -v "$PWD/demo/fixture:/workspace:ro" audisor:0.2.0 scan /workspace --json
```

After registry publication, `./scripts/install-docker.sh` or
`./scripts/install-docker.ps1` pulls `ghcr.io/itz1508/audisor:0.2.0` and
registers an equivalent stdio MCP transport. It does not mount a repository;
mount one explicitly for a scan or inspection command.

## Codex plugin

After native installation, add the marketplace and plugin from this repository:

```sh
codex plugin marketplace add itz1508/audisor --ref main
codex plugin add audisor@audisor
```

The plugin exposes the installed `audisor mcp` command and includes the Smart
Trace skill. Smart Trace is deliberately not a hook: it traces only ambiguous
or risky repair work after immutable inspection, not routine one-file edits.

## Expected demo evidence

`demo-output/` contains `inspection.json`, `trace.json`, `validation.json`,
`replay.json`, and `summary.json`. The summary reports one resolved scanner
finding, the `demo` entrypoint, a safe image diff, and that the source fixture
did not change. Artifacts contain redacted source evidence only.

No publish action occurs from these commands. PyPI and GHCR publication require
maintainer credentials and a separate explicit release action.
