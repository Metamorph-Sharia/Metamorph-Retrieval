# The retrieval layer as an image: the gateway (`metamorph-gateway serve`) and the market index's refresh, which the
# platform's market_index DAG runs (Metamorph-Knowledge-Platform/dags/market_index.py).
#   docker build -t metamorph/retrieval:dev Metamorph-Retrieval
# The models are baked in at pinned revisions (bge-m3 for meaning, the reranker's cross-encoder), so the tag names the
# exact models and a task never waits on Hugging Face; at run time the image reads only them (HF_HUB_OFFLINE).
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.9.27 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_HTTP_TIMEOUT=300 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH \
    HF_HOME=/models
RUN useradd --create-home --uid 1000 retrieval && mkdir /models && chown retrieval /models

WORKDIR /app
# Dependencies, then the models, then the code: a change to the code rebuilds only the last layers.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --all-packages --all-extras --no-install-workspace

# Only the files sentence-transformers loads; each repository's ref `main` names the revision baked, so the code loads
# the models by name.
ARG EMBEDDING_MODEL=BAAI/bge-m3
ARG EMBEDDING_REVISION=5617a9f61b028005a4858fdac845db406aefb181
ARG RERANKER_MODEL=cross-encoder/mmarco-mMiniLMv2-L12-H384-v1
ARG RERANKER_REVISION=1427fd652930e4ba29e8149678df786c240d8825
RUN python - <<'PY'
import os
from pathlib import Path
from huggingface_hub import snapshot_download

for model, revision, files in [
    (os.environ["EMBEDDING_MODEL"], os.environ["EMBEDDING_REVISION"],
     ["*.json", "1_Pooling/*", "pytorch_model.bin", "sentencepiece.bpe.model"]),
    (os.environ["RERANKER_MODEL"], os.environ["RERANKER_REVISION"], ["*.json", "model.safetensors", "sentencepiece.bpe.model"]),
]:
    snapshot_download(model, revision=revision, allow_patterns=files)
    refs = Path(os.environ["HF_HOME"], "hub", "models--" + model.replace("/", "--"), "refs")
    refs.mkdir(parents=True, exist_ok=True)
    (refs / "main").write_text(revision)
for path in Path(os.environ["HF_HOME"]).rglob("*"):  # readable by the task's user, retrieval
    path.chmod(0o755 if path.is_dir() else 0o644)
PY
ENV HF_HUB_OFFLINE=1
COPY packages ./packages
RUN uv sync --frozen --no-dev --all-packages --all-extras
COPY eval ./eval
COPY scripts ./scripts
RUN mkdir var && chown retrieval var

USER retrieval
CMD ["metamorph-gateway", "--help"]
