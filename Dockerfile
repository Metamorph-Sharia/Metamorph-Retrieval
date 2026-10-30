# The retrieval layer as an image: the gateway (`metamorph-gateway serve`) and the market index's refresh, which the
# platform's market_index DAG runs (Metamorph-Knowledge-Platform/dags/market_index.py).
#   docker build -t metamorph/retrieval:dev Metamorph-Retrieval
# Embedding models are downloaded into /models on first use; mount a volume there to keep them.
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.9.27 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH \
    HF_HOME=/models
RUN useradd --create-home --uid 1000 retrieval && mkdir /models && chown retrieval /models

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY packages ./packages
RUN uv sync --frozen --no-dev --all-packages --all-extras
COPY eval ./eval
COPY scripts ./scripts
RUN mkdir var && chown retrieval var

USER retrieval
CMD ["metamorph-gateway", "--help"]
