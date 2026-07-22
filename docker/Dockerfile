# ─────────────────────────────────────────────────────────────────────────────
# Audisor Toolkit (audisor-local) — independently runnable container
#
# Build context:  the audisor repository root (the directory above this one)
# Dockerfile:     docker/Dockerfile
#
# Build with (from the audisor repository root):
#   docker build -f docker/Dockerfile -t theoneshot-audisor-agent:0.9.0 .
#
# Frozen install: pinned dependency versions exported from backend/uv.lock via
#                 `uv export --frozen --no-hashes --no-emit-workspace --no-annotate --no-dev`.
#
# Docker Hub manifest observed for python:3.11-slim-bookworm on 2026-07-21.
# Update the tag and digest together only after an explicit image review.
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim-bookworm@sha256:b18992999dbe963a45a8a4da40ac2b1975be1a776d939d098c647482bcad5cba

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# ── Runtime dependencies (frozen from backend/uv.lock) ──────────────────────
COPY docker/requirements.txt /tmp/requirements.txt
RUN pip install --requirement /tmp/requirements.txt

# ── Install the audisor-local package (provides the `audisor` CLI) ──────────
RUN groupadd --gid 10001 audisor \
    && useradd --uid 10001 --gid 10001 --create-home --shell /usr/sbin/nologin audisor

WORKDIR /opt/audisor
COPY backend /opt/audisor/backend
RUN pip install /opt/audisor/backend

USER 10001:10001
ENTRYPOINT ["audisor"]
CMD ["mcp"]
