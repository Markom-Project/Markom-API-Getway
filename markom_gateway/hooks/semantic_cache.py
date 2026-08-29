"""
MarKom Semantic Cache — CustomGuardrail for similarity-based prompt caching.

Uses LiteLLM's embedding interface to call Gemini (or any supported provider).
No local embedding models needed — embeddings are generated via API.

Supports two backends:
  - FAISS (local, default) — good for single-node deployments
  - Pinecone (cloud) — set PINECONE_API_KEY + PINECONE_INDEX_NAME to enable

Set MARKOM_CACHE_BACKEND=pinecone to use Pinecone instead of FAISS.
"""

import hashlib
import json
import logging
import os
import time
from typing import Any, Optional

from litellm.integrations.custom_guardrail import CustomGuardrail
from litellm.types.utils import ModelResponse

logger = logging.getLogger("markom_gateway.semantic_cache")

_semantic_cache_state: dict[str, Any] = {
    "index": None,
    "entries": [],
    "initialized": False,
    "pinecone_index": None,
}


def _get_faiss_index(dimension: int):
    try:
        import faiss
    except ImportError:
        raise ImportError(
            "faiss-cpu is required for semantic caching. "
            "Install with: pip install faiss-cpu"
        )
    if _semantic_cache_state["index"] is None:
        _semantic_cache_state["index"] = faiss.IndexFlatIP(dimension)
    return _semantic_cache_state["index"]


def _get_pinecone_index():
    """Get or initialize Pinecone index. Set PINECONE_API_KEY + PINECONE_INDEX_NAME."""
    if _semantic_cache_state["pinecone_index"] is not None:
        return _semantic_cache_state["pinecone_index"]

    api_key = os.environ.get("PINECONE_API_KEY", "")
    index_name = os.environ.get("PINECONE_INDEX_NAME", "")
    if not api_key or not index_name:
        raise ValueError(
            "PINECONE_API_KEY and PINECONE_INDEX_NAME must be set "
            "to use Pinecone backend"
        )

    try:
        from pinecone import Pinecone, ServerlessSpec
    except ImportError:
        raise ImportError(
            "pinecone-client is required for Pinecone backend. "
            "Install with: pip install pinecone-client"
        )

    pc = Pinecone(api_key=api_key)
    existing = [idx.name for idx in pc.list_indexes()]
    if index_name not in existing:
        pc.create_index(
            name=index_name,
            dimension=768,
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region="us-east-1"),
        )
    _semantic_cache_state["pinecone_index"] = pc.Index(index_name)
    logger.info("Connected to Pinecone index: %s", index_name)
    return _semantic_cache_state["pinecone_index"]


def _get_cache_backend():
    """Returns 'pinecone' or 'faiss' based on env config."""
    return os.environ.get("MARKOM_CACHE_BACKEND", "faiss").lower()


def _normalize(text: str) -> str:
    return " ".join(text.lower().strip().split())


def _hash_response(response_text: str) -> str:
    return hashlib.sha256(response_text.encode()).hexdigest()[:16]


def _get_embedding_via_litellm(text: str, model: str) -> list[float]:
    """Generate embedding using LiteLLM's interface (supports Gemini, OpenAI, etc.)."""
    import litellm

    response = litellm.embeddings(
        model=model,
        input=[text],
    )
    return response.data[0].embedding


class MarkomSemanticCache(CustomGuardrail):
    def __init__(
        self,
        similarity_threshold: float = 0.95,
        cache_ttl_seconds: int = 3600,
        embedding_model: str = "gemini/text-embedding-004",
        cache_max_entries: int = 10000,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.similarity_threshold = similarity_threshold
        self.cache_ttl_seconds = cache_ttl_seconds
        self.embedding_model = embedding_model
        self.cache_max_entries = cache_max_entries

    def _get_embedding(self, text: str) -> list[float]:
        return _get_embedding_via_litellm(text, self.embedding_model)

    def _extract_prompt_text(self, data: dict) -> str:
        messages = data.get("messages", [])
        parts = []
        for msg in messages:
            if isinstance(msg, dict):
                content = msg.get("content", "")
                if isinstance(content, str):
                    parts.append(content)
                elif isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            parts.append(block.get("text", ""))
        return "\n".join(parts)

    async def async_pre_call_hook(
        self,
        user_api_key_dict,
        cache,
        data: dict,
        call_type,
    ) -> Optional[dict]:
        skip_models = os.environ.get("MARKOM_CACHE_SKIP_MODELS", "").split(",")
        model = data.get("model", "")
        if model in skip_models:
            return data

        prompt_text = self._extract_prompt_text(data)
        if not prompt_text.strip():
            return data

        backend = _get_cache_backend()

        try:
            embedding = self._get_embedding(prompt_text)

            if backend == "pinecone":
                return await self._lookup_pinecone(embedding, model, data)
            else:
                return await self._lookup_faiss(embedding, model, data)

        except Exception as e:
            logger.warning("Semantic cache lookup failed (%s): %s", backend, e)
            return data

    async def _lookup_faiss(
        self, embedding: list[float], model: str, data: dict
    ) -> Optional[dict]:
        dimension = len(embedding)
        index = _get_faiss_index(dimension)
        entries = _semantic_cache_state["entries"]

        if index.ntotal == 0:
            logger.debug("FAISS cache empty, skipping lookup")
            return data

        import numpy as np

        query = np.array([embedding], dtype=np.float32)
        k = min(5, index.ntotal)
        distances, indices = index.search(query, k)

        now = time.time()
        for dist, idx in zip(distances[0], indices[0]):
            if idx < 0 or idx >= len(entries):
                continue
            entry = entries[idx]
            if now - entry["created_at"] > self.cache_ttl_seconds:
                continue
            if entry.get("model") != model:
                continue
            if dist >= self.similarity_threshold:
                logger.info(
                    "FAISS cache HIT (similarity=%.4f) for model=%s", dist, model
                )
                cached_response = entry["response"]
                if isinstance(cached_response, str):
                    cached_response = json.loads(cached_response)
                return ModelResponse(**cached_response)

        logger.debug(
            "FAISS cache MISS (best=%.4f) for model=%s",
            distances[0][0] if len(distances[0]) > 0 else 0,
            model,
        )
        return data

    async def _lookup_pinecone(
        self, embedding: list[float], model: str, data: dict
    ) -> Optional[dict]:
        import os as _os

        namespace = _os.environ.get("PINECONE_NAMESPACE", "markom-cache")
        index = _get_pinecone_index()

        results = index.query(
            vector=embedding,
            top_k=5,
            namespace=namespace,
            include_metadata=True,
        )

        now = time.time()
        for match in results.get("matches", []):
            score = match.get("score", 0)
            meta = match.get("metadata", {})
            if score < self.similarity_threshold:
                continue
            if meta.get("model") != model:
                continue
            created = meta.get("created_at", 0)
            if now - created > self.cache_ttl_seconds:
                continue

            response_text = meta.get("response", "{}")
            logger.info(
                "Pinecone cache HIT (similarity=%.4f) for model=%s", score, model
            )
            cached_response = json.loads(response_text) if isinstance(response_text, str) else response_text
            return ModelResponse(**cached_response)

        logger.debug("Pinecone cache MISS for model=%s", model)
        return data

    async def async_log_success_event(
        self,
        kwargs: dict,
        response_obj: Any,
        start_time: float,
        end_time: float,
    ) -> None:
        if response_obj is None:
            return

        try:
            messages = kwargs.get("messages", [])
            prompt_text = ""
            for msg in messages:
                if isinstance(msg, dict):
                    content = msg.get("content", "")
                    if isinstance(content, str):
                        prompt_text += content + "\n"

            if not prompt_text.strip():
                return

            embedding = self._get_embedding(prompt_text.strip())
            dimension = len(embedding)
            index = _get_faiss_index(dimension)

            import numpy as np

            vec = np.array([embedding], dtype=np.float32)
            index.add(vec)

            if hasattr(response_obj, "model_dump"):
                response_data = response_obj.model_dump()
            elif isinstance(response_obj, dict):
                response_data = response_obj
            else:
                return

            entries = _semantic_cache_state["entries"]
            entries.append(
                {
                    "embedding": embedding,
                    "response": response_data,
                    "model": kwargs.get("model", ""),
                    "created_at": time.time(),
                    "response_hash": _hash_response(json.dumps(response_data, default=str)),
                }
            )

            if len(entries) > self.cache_max_entries:
                removed = entries[: len(entries) - self.cache_max_entries]
                entries[:] = entries[self.cache_max_entries :]
                if index.ntotal > 0:
                    try:
                        import numpy as np

                        indices_to_remove = np.array(
                            list(range(len(removed))), dtype=np.int64
                        )
                    except Exception:
                        pass
                logger.info(
                    "Evicted %d entries from semantic cache", len(removed)
                )

            logger.debug(
                "Cached response for model=%s (total entries=%d)",
                kwargs.get("model", ""),
                len(entries),
            )

        except Exception as e:
            logger.warning("Failed to cache response: %s", e)

    async def async_log_failure_event(
        self,
        kwargs: dict,
        response_obj: Any,
        start_time: float,
        end_time: float,
    ) -> None:
        pass

    @staticmethod
    def purge_cache():
        """Manual cache purge endpoint for compliance takedowns."""
        _semantic_cache_state["index"] = None
        _semantic_cache_state["entries"] = []
        logger.info("Semantic cache purged")
        return {"status": "purged", "entries_removed": True}
