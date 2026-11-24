FROM python:3.11-slim AS build
WORKDIR /build
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir --upgrade pip \
 && pip wheel --no-cache-dir --wheel-dir /wheels ".[api]"

FROM python:3.11-slim
RUN useradd --create-home --uid 10001 app
WORKDIR /app

COPY --from=build /wheels /wheels
RUN pip install --no-cache-dir /wheels/* && rm -rf /wheels

COPY configs ./configs
COPY data/manuals ./data/manuals
# Built by scripts/build_index.py in CD. If it's empty the service embeds on startup.
COPY artifacts/index ./artifacts/index

ENV PYTHONUNBUFFERED=1 \
    AGENT_CONFIG=/app/configs/config.yaml \
    PORT=8080

USER app
EXPOSE 8080
CMD exec uvicorn support_agent.api:app --host 0.0.0.0 --port ${PORT} --workers 2 --no-access-log
