"""Pre-compute manual embeddings so Cloud Run instances don't embed on cold start.

Run in CD (it has Vertex credentials) before `docker build`; the image copies
artifacts/index/ in. Also writes chunks.jsonl for inspection.

    GCP_PROJECT=my-proj python scripts/build_index.py
"""

import logging

from support_agent.config import get_config
from support_agent.factory import build_embedder
from support_agent.ingest import write_chunks
from support_agent.retrieval import build_retriever

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    cfg = get_config()
    retriever = build_retriever(cfg, embedder=build_embedder(cfg))
    out = cfg.path(cfg.retrieval["index_dir"])
    write_chunks(retriever.chunks, out / "chunks.jsonl")
    print(f"indexed {len(retriever.chunks)} chunks -> {out}")
