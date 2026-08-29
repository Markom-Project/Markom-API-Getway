"""
MarKom Health Router — CustomGuardrail for dynamic, health-based provider routing.

Records per-provider latency/error metrics via Redis and rewrites the routing
decision in async_pre_call_hook to prefer the healthiest provider.
"""

import logging
import os
import random
import time
from typing import Any, Optional

from litellm.integrations.custom_guardrail import CustomGuardrail

logger = logging.getLogger("markom_gateway.health_router")

_health_state: dict[str, Any] = {
    "redis": None,
    "initialized": False,
}

_METRICS_TTL = 600


class MarkomHealthRouter(CustomGuardrail):
    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        scoring_window_seconds: int = 300,
        exploration_rate: float = 0.02,
        latency_weight: float = 0.4,
        error_weight: float = 0.4,
        timeout_weight: float = 0.2,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.redis_url = redis_url
        self.scoring_window_seconds = scoring_window_seconds
        self.exploration_rate = exploration_rate
        self.latency_weight = latency_weight
        self.error_weight = error_weight
        self.timeout_weight = timeout_weight

    def _get_redis(self):
        if _health_state["redis"] is not None:
            return _health_state["redis"]
        try:
            import redis as redis_lib

            _health_state["redis"] = redis_lib.from_url(
                self.redis_url, decode_responses=True, socket_connect_timeout=2
            )
            _health_state["redis"].ping()
            logger.info("Health router connected to Redis: %s", self.redis_url)
            return _health_state["redis"]
        except Exception as e:
            logger.warning(
                "Health router Redis unavailable (%s), using in-memory fallback", e
            )
            _health_state["redis"] = _FallbackMetricsStore()
            return _health_state["redis"]

    def _get_provider_from_model(self, model: str) -> str:
        if "/" in model:
            return model.split("/")[0]
        for prefix in ["openai", "anthropic", "google", "azure", "bedrock", "cohere"]:
            if prefix in model.lower():
                return prefix
        return "unknown"

    def _compute_health_score(self, provider: str, redis_client) -> float:
        try:
            window_start = time.time() - self.scoring_window_seconds
            key_prefix = f"markom:health:{provider}"

            latencies = redis_client.zrangebyscore(
                f"{key_prefix}:latencies", window_start, "+inf"
            )
            errors = redis_client.zrangebyscore(
                f"{key_prefix}:errors", window_start, "+inf"
            )
            timeouts = redis_client.zrangebyscore(
                f"{key_prefix}:timeouts", window_start, "+inf"
            )

            total_requests = len(latencies) + len(errors) + len(timeouts)
            if total_requests == 0:
                return 0.5

            if latencies:
                lat_values = [float(l) for l in latencies]
                p50 = sorted(lat_values)[len(lat_values) // 2]
                latency_score = max(0, 1 - (p50 / 10.0))
            else:
                latency_score = 0.5

            error_rate = len(errors) / max(total_requests, 1)
            error_score = max(0, 1 - error_rate * 2)

            timeout_rate = len(timeouts) / max(total_requests, 1)
            timeout_score = max(0, 1 - timeout_rate * 3)

            score = (
                self.latency_weight * latency_score
                + self.error_weight * error_score
                + self.timeout_weight * timeout_score
            )

            return round(score, 4)

        except Exception as e:
            logger.warning("Failed to compute health score for %s: %s", provider, e)
            return 0.5

    async def async_pre_call_hook(
        self,
        user_api_key_dict,
        cache,
        data: dict,
        call_type,
    ) -> Optional[dict]:
        model = data.get("model", "")
        if not model:
            return data

        if random.random() < self.exploration_rate:
            logger.debug(
                "Exploration mode: skipping health routing for model=%s", model
            )
            return data

        redis_client = self._get_redis()
        provider = self._get_provider_from_model(model)

        metadata = data.get("metadata", {})
        fallbacks = metadata.get("fallbacks", [])

        if not fallbacks:
            return data

        scored_providers = []
        all_candidates = [provider] + [
            self._get_provider_from_model(f) for f in fallbacks
        ]

        for candidate_model, candidate_provider in zip(
            [model] + fallbacks, all_candidates
        ):
            score = self._compute_health_score(candidate_provider, redis_client)
            scored_providers.append((score, candidate_model, candidate_provider))
            logger.debug(
                "Provider %s (model=%s) health score: %.4f",
                candidate_provider,
                candidate_model,
                score,
            )

        scored_providers.sort(key=lambda x: x[0], reverse=True)
        best_score, best_model, best_provider = scored_providers[0]

        if best_model != model:
            logger.info(
                "Health routing: rerouting from %s (score=%.4f) to %s (score=%.4f)",
                model,
                scored_providers[-1][0] if len(scored_providers) > 1 else 0,
                best_model,
                best_score,
            )
            data["model"] = best_model

        return data

    async def async_log_success_event(
        self,
        kwargs: dict,
        response_obj: Any,
        start_time: float,
        end_time: float,
    ) -> None:
        model = kwargs.get("model", "")
        provider = self._get_provider_from_model(model)
        latency_ms = (end_time - start_time) * 1000

        redis_client = self._get_redis()
        now = time.time()

        try:
            key = f"markom:health:{provider}:latencies"
            redis_client.zadd(key, {str(latency_ms): now})
            redis_client.zremrangebyscore(key, 0, now - _METRICS_TTL)
            redis_client.expire(key, _METRICS_TTL)
        except Exception as e:
            logger.debug("Failed to record latency metric: %s", e)

    async def async_log_failure_event(
        self,
        kwargs: dict,
        response_obj: Any,
        start_time: float,
        end_time: float,
    ) -> None:
        model = kwargs.get("model", "")
        provider = self._get_provider_from_model(model)
        redis_client = self._get_redis()
        now = time.time()

        try:
            exception = kwargs.get("exception", None)
            is_timeout = isinstance(exception, TimeoutError) or (
                exception and "timeout" in str(exception).lower()
            )
            key_suffix = "timeouts" if is_timeout else "errors"
            key = f"markom:health:{provider}:{key_suffix}"
            redis_client.zadd(key, {str(now): now})
            redis_client.zremrangebyscore(key, 0, now - _METRICS_TTL)
            redis_client.expire(key, _METRICS_TTL)
        except Exception as e:
            logger.debug("Failed to record error metric: %s", e)


class _FallbackMetricsStore:
    """In-memory fallback when Redis is unavailable."""

    def __init__(self):
        self._store: dict[str, list[tuple[float, float]]] = {}

    def zadd(self, key: str, mapping: dict):
        if key not in self._store:
            self._store[key] = []
        for score_str, member in mapping.items():
            self._store[key].append((float(score_str), member))

    def zrangebyscore(self, key: str, min_score: float, max_score: str):
        if key not in self._store:
            return []
        now = time.time()
        self._store[key] = [
            (s, m)
            for s, m in self._store[key]
            if s >= min_score and (max_score == "+inf" or s <= float(max_score))
        ]
        return [m for _, m in self._store[key]]

    def zremrangebyscore(self, key: str, min_score: float, max_score: float):
        if key not in self._store:
            return
        self._store[key] = [
            (s, m) for s, m in self._store[key] if not (min_score <= s <= max_score)
        ]

    def expire(self, key: str, ttl: int):
        pass

    def ping(self):
        return True
