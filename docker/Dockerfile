FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN groupadd --gid 10001 audisor \
    && useradd --uid 10001 --gid 10001 --create-home --shell /usr/sbin/nologin audisor

WORKDIR /opt/audisor
COPY backend /opt/audisor/backend
RUN pip install --no-cache-dir /opt/audisor/backend

USER 10001:10001
ENTRYPOINT ["audisor"]
CMD ["mcp"]
