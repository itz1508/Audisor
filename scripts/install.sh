#!/usr/bin/env sh
set -eu

PACKAGE="${AUDISOR_PACKAGE:-audisor-local==0.2.0}"
if ! command -v uv >/dev/null 2>&1; then
  printf '%s\n' 'uv is required. Install it from https://docs.astral.sh/uv/.' >&2
  exit 1
fi

uv tool install --force "$PACKAGE"
if [ "${1:-}" != "--skip-codex-registration" ]; then
  audisor install-codex
fi
