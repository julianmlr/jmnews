FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY src/ ./src/

RUN pip install --no-cache-dir --upgrade pip \
    && pip wheel --no-cache-dir --wheel-dir /wheels .


FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Europe/Berlin

RUN apt-get update && apt-get install -y --no-install-recommends \
    tzdata \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /bin/bash jmnews

WORKDIR /app

COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir --no-index --find-links /wheels jmnews \
    && rm -rf /wheels

COPY jm_profile.md ./jm_profile.md

RUN mkdir -p /app/data/briefings /app/data/logs \
    && chown -R jmnews:jmnews /app

USER jmnews

ENV JMNEWS_DB_PATH=/app/data/jmnews.db \
    JMNEWS_PROFILE_PATH=/app/jm_profile.md \
    JMNEWS_BRIEFINGS_DIR=/app/data/briefings \
    JMNEWS_LOG_DIR=/app/data/logs

ENTRYPOINT ["python", "-m", "jmnews.main"]
CMD ["run-daemon"]
