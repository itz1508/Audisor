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

Prerequisite: Docker Engine. For the submitted public image, no GHCR login is required:

```sh
docker logout ghcr.io
docker pull ghcr.io/itz1508/theoneshot-audisor-agent:submission-20260721
docker run --rm ghcr.io/itz1508/theoneshot-audisor-agent:submission-20260721 --help
docker run --rm ghcr.io/itz1508/theoneshot-audisor-agent:submission-20260721 scan --help
```

To scan a repository, mount it explicitly as read-only:

```sh
docker run --rm --read-only --user 10001:10001 \
  -v "$PWD/demo/fixture:/workspace:ro" \
  ghcr.io/itz1508/theoneshot-audisor-agent:submission-20260721 scan /workspace --json
```

`./scripts/install-docker.sh` and `./scripts/install-docker.ps1` default to `ghcr.io/itz1508/theoneshot-audisor-agent:submission-20260721` and register an equivalent stdio MCP transport. They do not mount a repository; mount one explicitly for a scan or inspection command.

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
