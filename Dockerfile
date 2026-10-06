ARG PYTHON_VERSION=3.13
FROM python:${PYTHON_VERSION}-slim AS base
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /code

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_CACHE_DIR=/code/.uv-cache

# ====== Builder (runtime venv) ==========
FROM base AS builder

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# ====== Dev Builder ======
FROM base AS dev-builder
COPY --from=builder /code/.venv /code/.venv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --group dev

# ====== Dev =======
FROM base AS dev
COPY --from=dev-builder /code/.venv /code/.venv
ENV PATH="/code/.venv/bin:${PATH}"
COPY . .

USER runner
EXPOSE 8000
ENTRYPOINT [ "/code/docker-entrypoint.sh" ]

# ====== Prod =======
FROM base AS prod
COPY --from=builder /code/.venv /code/.venv
ENV PATH="/code/.venv/bin:${PATH}"
COPY app ./app
COPY scripts ./scripts
COPY docker-entrypoint.sh ./

RUN chmod +x /code/docker-entrypoint.sh

RUN chown -R runner:root /code \
    && chmod -R g=u /code

USER runner
EXPOSE 8000
ENTRYPOINT [ "/code/docker-entrypoint.sh" ]
