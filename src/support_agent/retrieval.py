"""Hybrid retrieval: BM25 + dense embeddings, fused with reciprocal rank fusion.

BM25 alone is surprisingly good on manuals because users quote error codes and
LED colors verbatim ("E74", "blinking red"). Dense retrieval covers paraphrases
("it keeps turning off and on" -> short cycling). RRF combines them without
having to calibrate the two score scales against each other.

The corpus is a few hundred chunks, so everything lives in memory. The dense
index is cached to disk so we don't re-embed on every cold start.
"""

from __future__ import annotations

import logging
import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np

from support_agent.ingest import Chunk

log = logging.getLogger(__name__)

_TOKEN = re.compile(r"[a-z0-9]+(?:\.[0-9]+)?")
# fmt: off
STOPWORDS = frozenset({
    "a", "an", "the", "and", "or", "but", "if", "of", "to", "in", "on", "at", "for",
    "with", "from", "by", "is", "are", "was", "were", "be", "been", "it", "its",
    "this", "that", "these", "those", "my", "our", "your", "i", "me", "we", "you",
    "do", "does", "did", "how", "what", "why", "when", "where", "which", "can",
    "could", "should", "would", "will", "just", "so", "not", "no", "there", "their",
    "they", "them", "as", "up", "out", "about"
})
# fmt: on

# Words users actually type -> device_type in the manuals' front matter.
DEVICE_ALIASES: dict[str, tuple[str, ...]] = {
    "thermostat": ("thermostat", "t3", "heating", "furnace", "hvac", "c-wire", "c wire"),
    "smart_plug": ("plug", "p1", "outlet"),
    "doorbell": ("doorbell", "d2", "chime"),
    "smart_lock": ("lock", "l1", "deadbolt", "keypad", "doorsense"),
    "hub": ("hub", "h1", "zigbee", "matter"),
    "bulb": ("bulb", "b2", "light bulb", "lamp", "dimmer"),
    "smoke_alarm": ("smoke", "co alarm", "carbon monoxide", "s1", "detector"),
    "camera": ("camera", "c1", "microsd", "sd card", "privacy mode", "pan"),
}


def _stem(t: str) -> str:
    # Crude suffix stripping. Good enough for "flickering"/"flickers"/"flicker";
    # a real stemmer buys almost nothing on a corpus this small.
    if len(t) <= 4 or t[0].isdigit():
        return t
    for suffix in ("ing", "ed", "es", "s"):
        if t.endswith(suffix) and len(t) - len(suffix) >= 3:
            return t[: -len(suffix)]
    return t


def tokenize(text: str) -> list[str]:
    return [_stem(t) for t in _TOKEN.findall(text.lower()) if t not in STOPWORDS]


def detect_device_types(text: str) -> set[str]:
    t = f" {text.lower()} "
    found = set()
    for device, aliases in DEVICE_ALIASES.items():
        for a in aliases:
            if re.search(rf"(?<![a-z0-9]){re.escape(a)}(?![a-z0-9])", t):
                found.add(device)
                break
    return found


class BM25:
    def __init__(self, docs: list[str], k1: float = 1.4, b: float = 0.75):
        self.k1, self.b = k1, b
        self.tokens = [tokenize(d) for d in docs]
        self.tf = [Counter(t) for t in self.tokens]
        self.lens = np.array([len(t) for t in self.tokens], dtype=float)
        self.avgdl = float(self.lens.mean()) if len(docs) else 0.0
        df = Counter(term for toks in self.tokens for term in set(toks))
        n = len(docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def scores(self, query: str) -> np.ndarray:
        q = tokenize(query)
        out = np.zeros(len(self.tokens))
        for i, tf in enumerate(self.tf):
            norm = self.k1 * (1 - self.b + self.b * self.lens[i] / self.avgdl)
            s = 0.0
            for term in q:
                if term in tf:
                    f = tf[term]
                    s += self.idf[term] * f * (self.k1 + 1) / (f + norm)
            out[i] = s
        return out


class Embedder(Protocol):
    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...


@dataclass
class Hit:
    chunk: Chunk
    score: float  # fused RRF score
    bm25: float
    dense: float | None = None


class HybridRetriever:
    def __init__(
        self,
        chunks: list[Chunk],
        embedder: Embedder | None = None,
        rrf_k: int = 60,
        cache_dir: str | Path | None = None,
    ):
        self.chunks = chunks
        self.rrf_k = rrf_k
        # Section title + model name are included so "doorbell battery" matches
        # the "Battery and charging" section of the doorbell manual.
        self._texts = [f"{c.model} {c.section}\n{c.text}" for c in chunks]
        self.bm25 = BM25(self._texts)
        self.embedder = embedder
        self.vectors = self._load_or_embed(cache_dir) if embedder else None
        self.dense_failures = 0

    def _load_or_embed(self, cache_dir: str | Path | None) -> np.ndarray:
        ids = [c.id for c in self.chunks]
        if cache_dir:
            path = Path(cache_dir) / "vectors.npz"
            if path.exists():
                data = np.load(path, allow_pickle=False)
                if list(data["ids"]) == ids:
                    log.info("loaded cached embeddings for %d chunks", len(ids))
                    return data["vectors"]
        vecs = np.asarray(self.embedder.embed_documents(self._texts), dtype=np.float32)
        vecs /= np.linalg.norm(vecs, axis=1, keepdims=True) + 1e-9
        if cache_dir:
            Path(cache_dir).mkdir(parents=True, exist_ok=True)
            np.savez(Path(cache_dir) / "vectors.npz", ids=np.array(ids), vectors=vecs)
        return vecs

    def search(self, query: str, k: int = 5, device_type: str | None = None) -> list[Hit]:
        candidates = self._candidate_mask(query, device_type)
        bm25 = self.bm25.scores(query)
        bm25 = np.where(candidates, bm25, -np.inf)
        ranks = [np.argsort(-bm25)]

        dense = None
        if self.vectors is not None:
            try:
                q = np.asarray(self.embedder.embed_query(query), dtype=np.float32)
            except Exception:  # noqa: BLE001
                # Embedding quota is per base model and much lower than the LLM's.
                # BM25 alone still finds the right section for most questions, so a
                # 429 here degrades the ranking instead of failing the search.
                self.dense_failures += 1
                log.warning("query embedding failed, using BM25 only", exc_info=True)
            else:
                q /= np.linalg.norm(q) + 1e-9
                dense = self.vectors @ q
                ranks.append(np.argsort(-np.where(candidates, dense, -np.inf)))

        fused = np.zeros(len(self.chunks))
        for order in ranks:
            for rank, idx in enumerate(order):
                if candidates[idx]:
                    fused[idx] += 1.0 / (self.rrf_k + rank + 1)

        top = [i for i in np.argsort(-fused) if candidates[i]][:k]
        return [
            Hit(
                chunk=self.chunks[i],
                score=float(fused[i]),
                bm25=float(bm25[i]),
                dense=float(dense[i]) if dense is not None else None,
            )
            for i in top
        ]

    def _candidate_mask(self, query: str, device_type: str | None) -> np.ndarray:
        """Restrict to the device(s) the user is asking about when we can tell.

        Without this, generic sections ("Factory reset", "Warranty") from the
        wrong device often outrank the right one.
        """
        types = {device_type} if device_type else detect_device_types(query)
        if not types:
            return np.ones(len(self.chunks), dtype=bool)
        mask = np.array([c.device_type in types for c in self.chunks])
        return mask if mask.any() else np.ones(len(self.chunks), dtype=bool)


def build_retriever(cfg, embedder: Embedder | None = None) -> HybridRetriever:
    from support_agent.ingest import load_manuals

    chunks = load_manuals(cfg.path(cfg.retrieval["manuals_dir"]))
    return HybridRetriever(
        chunks,
        embedder=embedder,
        rrf_k=cfg.retrieval["rrf_k"],
        cache_dir=cfg.path(cfg.retrieval["index_dir"]),
    )
