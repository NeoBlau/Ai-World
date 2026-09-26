"""Embeddings for semantic memory.

Uses OpenAI / Gemini / Ollama embeddings when configured, otherwise a local
feature-hashing embedding (unigrams + bigrams, signed hashing, log-TF,
L2-normalised). The hashing embedding is deterministic, free and gives real
lexical-semantic similarity, which keeps memory search working offline.

All vectors are normalised to ``EMBEDDING_DIM`` so they fit one pgvector column.
Each memory row stores which model produced its vector; retrieval only
compares vectors from the same model.
"""

from __future__ import annotations

import hashlib
import json
import math
import re

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.core.redis import get_redis
from app.llm.base import LLMProvider, ProviderError
from app.models.memory import EMBEDDING_DIM

log = get_logger("aiworld.embeddings")

_TOKEN = re.compile(r"[a-zA-Z0-9À-ɏЀ-ӿ]+")
_STOP = set(
    "a an the and or but if then of to in on at for with about from by is are was were be been being it its this that "
    "these those i you he she we they me my your our their them his her as so do does did not no yes can could would "
    "should will just very really also too into over than more most some any all what which who whom how why when where".split()
)
HASH_MODEL = "hash-384"


def _stem(tok: str) -> str:
    for suf in ("ing", "ies", "es", "ed", "ly", "s"):
        if len(tok) > len(suf) + 3 and tok.endswith(suf):
            return tok[: -len(suf)] + ("y" if suf == "ies" else "")
    return tok


def tokenize(text: str) -> list[str]:
    return [_stem(t) for t in (m.group(0).lower() for m in _TOKEN.finditer(text)) if t not in _STOP and len(t) > 1]


def hash_embed(text: str, dim: int = EMBEDDING_DIM) -> list[float]:
    toks = tokenize(text)
    feats: dict[str, float] = {}
    for t in toks:
        feats[t] = feats.get(t, 0.0) + 1.0
    for a, b in zip(toks, toks[1:]):
        k = f"{a}_{b}"
        feats[k] = feats.get(k, 0.0) + 0.5
    vec = [0.0] * dim
    for feat, tf in feats.items():
        h = hashlib.blake2b(feat.encode(), digest_size=8).digest()
        idx = int.from_bytes(h[:4], "little") % dim
        sign = 1.0 if h[4] & 1 else -1.0
        vec[idx] += sign * (1.0 + math.log(tf))
    return _normalise(vec, dim)


def _normalise(vec: list[float], dim: int = EMBEDDING_DIM) -> list[float]:
    vec = list(vec[:dim]) + [0.0] * max(0, dim - len(vec))
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0:
        return vec
    return [v / norm for v in vec]


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


class EmbeddingService:
    def __init__(self, settings: Settings | None = None, providers: dict[str, LLMProvider] | None = None) -> None:
        self.settings = settings or get_settings()
        self._providers = providers

    def _provider(self) -> LLMProvider | None:
        if self._providers is None:
            from app.llm.router import get_router

            self._providers = get_router().providers
        choice = self.settings.embedding_provider.lower()
        if choice == "hash":
            return None
        if choice == "auto":
            for name in ("openai", "gemini"):
                p = self._providers.get(name)
                if p and p.is_configured():
                    return p
            return None
        p = self._providers.get(choice)
        return p if p and p.is_configured() else None

    @property
    def model_name(self) -> str:
        p = self._provider()
        return f"{p.name}-{EMBEDDING_DIM}" if p else HASH_MODEL

    async def embed(self, texts: list[str]) -> tuple[list[list[float]], str]:
        """Return (vectors, model_name). Falls back to hashing on any provider error."""
        if not texts:
            return [], self.model_name
        prov = self._provider()
        if prov is None:
            return [hash_embed(t) for t in texts], HASH_MODEL
        model = f"{prov.name}-{EMBEDDING_DIM}"
        r = get_redis()
        keys = [f"emb:{model}:{hashlib.sha1(t.encode()).hexdigest()}" for t in texts]
        cached = await r.mget(keys)
        out: list[list[float] | None] = [json.loads(c) if c else None for c in cached]
        missing = [i for i, v in enumerate(out) if v is None]
        if missing:
            try:
                vecs = await prov.embed([texts[i] for i in missing])
            except (ProviderError, KeyError, TypeError) as exc:
                log.warning("embedding provider failed, using hash embedding", extra={"provider": prov.name, "error": str(exc)})
                return [hash_embed(t) for t in texts], HASH_MODEL
            if not vecs or len(vecs) != len(missing):
                return [hash_embed(t) for t in texts], HASH_MODEL
            pipe = r.pipeline()
            for i, v in zip(missing, vecs):
                nv = _normalise(v)
                out[i] = nv
                pipe.set(keys[i], json.dumps(nv), ex=86400)
            await pipe.execute()
        return [v for v in out if v is not None], model

    async def embed_one(self, text: str) -> tuple[list[float], str]:
        vecs, model = await self.embed([text])
        return vecs[0], model


_service: EmbeddingService | None = None


def get_embedding_service() -> EmbeddingService:
    global _service
    if _service is None:
        _service = EmbeddingService()
    return _service
