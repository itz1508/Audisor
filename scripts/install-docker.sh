#!/usr/bin/env sh
set -eu

IMAGE="${AUDISOR_IMAGE:-ghcr.io/itz1508/audisor:0.2.0}"
if ! command -v docker >/dev/null 2>&1; then
  printf '%s\n' 'Docker is required for the container installation path.' >&2
  exit 1
fi

docker pull "$IMAGE"
if [ "${1:-}" != "--skip-codex-registration" ]; then
  codex mcp add audisor-docker -- docker run --rm -i --read-only --user 10001:10001 "$IMAGE" mcp
fi
