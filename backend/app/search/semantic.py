"""Embedding providers for semantic search.

The default provider is a dependency-free hashed TF-IDF vectoriser with synonym
folding; it captures the marine-electrical vocabulary well enough for
document-scale retrieval and needs no model download. A hosted provider
(Voyage AI) is used automatically when an API key is configured. Providers
share the interface, so a local transformer model can be dropped in later.
"""
from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol

import numpy as np

from ..config import get_settings
from .synonyms import SYNONYM_GROUPS

_TOKEN_RE = re.compile(r"[a-z0-9]+(?:[/.\-][a-z0-9]+)*|°c|°f|mm²|ω")
_STOP = set("the a an and or of to in on for with by is are be as at from this that it its into than then when which will can may".split())

_CANON: dict[str, str] = {}
for group in SYNONYM_GROUPS:
    head = group[0]
    for term in group:
        if len(term) < 2 or term in ("a", "v", "w", "+", "-", "pe"):
            continue  # single letters/units are too ambiguous to fold
        _CANON[term] = head


def tokenize(text: str) -> list[str]:
    t = text.lower()
    # Fold multi-word synonyms into a canonical token first.
    for term, head in sorted(_CANON.items(), key=lambda kv: len(kv[0]), reverse=True):
        if " " in term and term in t:
            t = t.replace(term, head.replace(" ", "_"))
    toks = []
    for tok in _TOKEN_RE.findall(t):
        tok = _CANON.get(tok, tok).replace(" ", "_")
        if tok in _STOP or len(tok) < 2 and not tok.isdigit():
            continue
        toks.append(tok)
    # bigrams give some phrase sensitivity
    bigrams = [f"{a}_{b}" for a, b in zip(toks, toks[1:])]
    return toks + bigrams


class EmbeddingProvider(Protocol):
    name: str
    dim: int

    def embed(self, texts: list[str]) -> np.ndarray: ...

    def embed_query(self, text: str) -> np.ndarray: ...


class HashedTfidfProvider:
    name = "local-hashed-tfidf"
    dim = 4096

    def _index(self, tok: str) -> int:
        return int(hashlib.blake2b(tok.encode(), digest_size=4).hexdigest(), 16) % self.dim

    def _vector(self, text: str) -> np.ndarray:
        v = np.zeros(self.dim, dtype=np.float32)
        toks = tokenize(text)
        if not toks:
            return v
        counts: dict[str, int] = {}
        for t in toks:
            counts[t] = counts.get(t, 0) + 1
        for t, c in counts.items():
            weight = 1.0 + math.log(c)
            if "_" in t:
                weight *= 0.7  # bigrams
            if re.fullmatch(r"[\d.,/]+", t):
                weight *= 1.3  # numbers matter in technical search
            v[self._index(t)] += weight
        n = np.linalg.norm(v)
        return v / n if n else v

    def embed(self, texts: list[str]) -> np.ndarray:
        return np.stack([self._vector(t) for t in texts]) if texts else np.zeros((0, self.dim), dtype=np.float32)

    def embed_query(self, text: str) -> np.ndarray:
        return self._vector(text)


class VoyageProvider:
    """Voyage AI embeddings over plain HTTPS (no extra dependency)."""

    name = "voyage"
    dim = 512

    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model
        self.name = f"voyage:{model}"

    def _call(self, texts: list[str], input_type: str) -> np.ndarray:
        import httpx

        resp = httpx.post(
            "https://api.voyageai.com/v1/embeddings",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={"input": texts, "model": self.model, "input_type": input_type},
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()["data"]
        arr = np.array([d["embedding"] for d in data], dtype=np.float32)
        self.dim = arr.shape[1]
        return arr

    def embed(self, texts: list[str]) -> np.ndarray:
        out = []
        for i in range(0, len(texts), 64):
            out.append(self._call(texts[i : i + 64], "document"))
        return np.concatenate(out) if out else np.zeros((0, self.dim), dtype=np.float32)

    def embed_query(self, text: str) -> np.ndarray:
        return self._call([text], "query")[0]


_provider: EmbeddingProvider | None = None


def get_embedding_provider() -> EmbeddingProvider:
    global _provider
    if _provider is None:
        s = get_settings()
        if s.voyage_api_key:
            _provider = VoyageProvider(s.voyage_api_key, s.voyage_model)
        else:
            _provider = HashedTfidfProvider()
    return _provider
