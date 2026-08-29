"""
MarKom Audit Logger — CustomLogger for structured, append-only audit trail.

Captures every request as an immutable JSON record for DPDPA compliance.
Supports configurable retention and content redaction.
"""

import json
import logging
import os
import time
from typing import Any, Optional

from litellm.integrations.custom_logger import CustomLogger

logger = logging.getLogger("markom_gateway.audit_logger")

_audit_store: list[dict[str, Any]] = []

_db_pool = None


def _get_db_pool():
    global _db_pool
    if _db_pool is not None:
        return _db_pool
    dsn = os.environ.get("MARKOM_AUDIT_DB_URL") or os.environ.get("DATABASE_URL")
    if not dsn:
        logger.warning(
            "No MARKOM_AUDIT_DB_URL or DATABASE_URL set; audit records stored in memory only"
        )
        return None
    try:
        import psycopg_pool

        _db_pool = psycopg_pool.ConnectionPool(dsn, min_size=1, max_size=5)
        _ensure_audit_table(_db_pool)
        logger.info("Audit logger connected to Postgres")
        return _db_pool
    except Exception as e:
        logger.warning("Failed to connect to Postgres for audit: %s", e)
        return None


def _ensure_audit_table(pool):
    try:
        with pool.connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS markom_audit_log (
                    id BIGSERIAL PRIMARY KEY,
                    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    request_id TEXT,
                    user_id TEXT,
                    team_id TEXT,
                    api_key_hash TEXT,
                    model TEXT,
                    provider TEXT,
                    prompt_tokens INT,
                    completion_tokens INT,
                    total_tokens INT,
                    cost_usd FLOAT,
                    latency_ms FLOAT,
                    status TEXT,
                    error_message TEXT,
                    guardrail_results JSONB,
                    routing_decision JSONB,
                    metadata JSONB,
                    prompt_content TEXT,
                    response_content TEXT,
                    UNIQUE(request_id)
                );
                CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON markom_audit_log (timestamp);
                CREATE INDEX IF NOT EXISTS idx_audit_user ON markom_audit_log (user_id);
                CREATE INDEX IF NOT EXISTS idx_audit_team ON markom_audit_log (team_id);
                CREATE INDEX IF NOT EXISTS idx_audit_model ON markom_audit_log (model);
                CREATE INDEX IF NOT EXISTS idx_audit_status ON markom_audit_log (status);
                """
            )
            conn.commit()
    except Exception as e:
        logger.error("Failed to create audit table: %s", e)


def _get_provider_from_model(model: str) -> str:
    if "/" in model:
        return model.split("/")[0]
    for prefix in ["openai", "anthropic", "google", "azure", "bedrock", "cohere"]:
        if prefix in model.lower():
            return prefix
    return "unknown"


def _hash_api_key(api_key: str) -> str:
    if not api_key:
        return ""
    import hashlib

    return hashlib.sha256(api_key.encode()).hexdigest()[:16]


class MarkomAuditLogger(CustomLogger):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.redact_content = os.environ.get(
            "MARKOM_AUDIT_REDACT_CONTENT", "false"
        ).lower() == "true"

    async def async_log_success_event(
        self,
        kwargs: dict,
        response_obj: Any,
        start_time: float,
        end_time: float,
    ) -> None:
        record = self._build_record(kwargs, response_obj, start_time, end_time, "success")
        self._store_record(record)

    async def async_log_failure_event(
        self,
        kwargs: dict,
        response_obj: Any,
        start_time: float,
        end_time: float,
    ) -> None:
        record = self._build_record(kwargs, response_obj, start_time, end_time, "failure")
        self._store_record(record)

    def _build_record(
        self,
        kwargs: dict,
        response_obj: Any,
        start_time: float,
        end_time: float,
        status: str,
    ) -> dict[str, Any]:
        model = kwargs.get("model", "unknown")
        latency_ms = round((end_time - start_time) * 1000, 2)

        user_api_key_dict = kwargs.get("user_api_key_dict", {})
        api_key = ""
        if hasattr(user_api_key_dict, "api_key"):
            api_key = user_api_key_dict.api_key or ""
        elif isinstance(user_api_key_dict, dict):
            api_key = user_api_key_dict.get("api_key", "")

        prompt_tokens = 0
        completion_tokens = 0
        total_tokens = 0
        cost = 0.0

        if response_obj is not None:
            if hasattr(response_obj, "usage"):
                usage = response_obj.usage
                if usage:
                    prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
                    completion_tokens = getattr(usage, "completion_tokens", 0) or 0
                    total_tokens = getattr(usage, "total_tokens", 0) or 0
            if hasattr(response_obj, "usage") and response_obj.usage:
                cost = getattr(response_obj, "response_cost", 0.0) or 0.0

        prompt_content = None
        response_content = None
        if not self.redact_content:
            messages = kwargs.get("messages", [])
            if messages:
                prompt_content = json.dumps(messages, default=str)[:10000]
            if response_obj is not None and hasattr(response_obj, "choices"):
                choices = response_obj.choices
                if choices:
                    choice = choices[0]
                    if hasattr(choice, "message") and choice.message:
                        response_content = str(choice.message.content)[:10000]

        metadata = kwargs.get("metadata", {})
        routing_decision = metadata.get("routing_decision", {})

        record = {
            "timestamp": time.time(),
            "request_id": metadata.get("request_id", ""),
            "user_id": getattr(user_api_key_dict, "user_id", "")
            if hasattr(user_api_key_dict, "user_id")
            else (user_api_key_dict.get("user_id", "") if isinstance(user_api_key_dict, dict) else ""),
            "team_id": getattr(user_api_key_dict, "team_id", "")
            if hasattr(user_api_key_dict, "team_id")
            else (user_api_key_dict.get("team_id", "") if isinstance(user_api_key_dict, dict) else ""),
            "api_key_hash": _hash_api_key(api_key),
            "model": model,
            "provider": _get_provider_from_model(model),
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "cost_usd": cost,
            "latency_ms": latency_ms,
            "status": status,
            "error_message": str(response_obj) if status == "failure" else None,
            "guardrail_results": metadata.get("guardrail_results", {}),
            "routing_decision": routing_decision,
            "metadata": {k: v for k, v in metadata.items() if k not in ("guardrail_results", "routing_decision")},
            "prompt_content": prompt_content,
            "response_content": response_content,
        }

        return record

    def _store_record(self, record: dict[str, Any]) -> None:
        _audit_store.append(record)

        pool = _get_db_pool()
        if pool is not None:
            try:
                with pool.connection() as conn:
                    conn.execute(
                        """
                        INSERT INTO markom_audit_log (
                            timestamp, request_id, user_id, team_id, api_key_hash,
                            model, provider, prompt_tokens, completion_tokens,
                            total_tokens, cost_usd, latency_ms, status,
                            error_message, guardrail_results, routing_decision,
                            metadata, prompt_content, response_content
                        ) VALUES (
                            to_timestamp(%(timestamp)s), %(request_id)s, %(user_id)s,
                            %(team_id)s, %(api_key_hash)s, %(model)s, %(provider)s,
                            %(prompt_tokens)s, %(completion_tokens)s, %(total_tokens)s,
                            %(cost_usd)s, %(latency_ms)s, %(status)s,
                            %(error_message)s, %(guardrail_results)s::jsonb,
                            %(routing_decision)s::jsonb, %(metadata)s::jsonb,
                            %(prompt_content)s, %(response_content)s
                        )
                        ON CONFLICT (request_id) DO NOTHING
                        """,
                        {
                            **record,
                            "guardrail_results": json.dumps(record["guardrail_results"], default=str),
                            "routing_decision": json.dumps(record["routing_decision"], default=str),
                            "metadata": json.dumps(record["metadata"], default=str),
                        },
                    )
                    conn.commit()
            except Exception as e:
                logger.error("Failed to write audit record to Postgres: %s", e)

        if len(_audit_store) % 100 == 0:
            logger.info("Audit log in-memory buffer size: %d", len(_audit_store))

    @staticmethod
    def get_audit_records(
        limit: int = 100,
        offset: int = 0,
        user_id: str = None,
        team_id: str = None,
        model: str = None,
        status: str = None,
        start_time: float = None,
        end_time: float = None,
    ) -> list[dict]:
        pool = _get_db_pool()
        if pool is not None:
            try:
                conditions = []
                params = {}
                if user_id:
                    conditions.append("user_id = %(user_id)s")
                    params["user_id"] = user_id
                if team_id:
                    conditions.append("team_id = %(team_id)s")
                    params["team_id"] = team_id
                if model:
                    conditions.append("model = %(model)s")
                    params["model"] = model
                if status:
                    conditions.append("status = %(status)s")
                    params["status"] = status
                if start_time:
                    conditions.append("timestamp >= to_timestamp(%(start_time)s)")
                    params["start_time"] = start_time
                if end_time:
                    conditions.append("timestamp <= to_timestamp(%(end_time)s)")
                    params["end_time"] = end_time

                where = " AND ".join(conditions) if conditions else "1=1"
                params["limit"] = limit
                params["offset"] = offset

                with pool.connection() as conn:
                    cursor = conn.execute(
                        f"SELECT * FROM markom_audit_log WHERE {where} ORDER BY timestamp DESC LIMIT %(limit)s OFFSET %(offset)s",
                        params,
                    )
                    columns = [desc[0] for desc in cursor.description]
                    return [dict(zip(columns, row)) for row in cursor.fetchall()]
            except Exception as e:
                logger.error("Failed to query audit records: %s", e)

        return [
            r for r in reversed(_audit_store[-limit - offset : -offset or None])
            if (user_id is None or r.get("user_id") == user_id)
            and (team_id is None or r.get("team_id") == team_id)
            and (model is None or r.get("model") == model)
            and (status is None or r.get("status") == status)
        ]

    @staticmethod
    def export_records_csv(
        user_id: str = None,
        team_id: str = None,
        start_time: float = None,
        end_time: float = None,
    ) -> str:
        records = MarkomAuditLogger.get_audit_records(
            limit=10000, user_id=user_id, team_id=team_id,
            start_time=start_time, end_time=end_time,
        )
        if not records:
            return "No records found"

        import csv
        import io

        output = io.StringIO()
        if records:
            writer = csv.DictWriter(output, fieldnames=records[0].keys())
            writer.writeheader()
            writer.writerows(records)
        return output.getvalue()

    @staticmethod
    def get_stats() -> dict:
        pool = _get_db_pool()
        if pool is not None:
            try:
                with pool.connection() as conn:
                    cursor = conn.execute(
                        """
                        SELECT
                            COUNT(*) as total_requests,
                            COUNT(*) FILTER (WHERE status = 'success') as successes,
                            COUNT(*) FILTER (WHERE status = 'failure') as failures,
                            AVG(latency_ms) as avg_latency_ms,
                            SUM(cost_usd) as total_cost_usd,
                            SUM(prompt_tokens) as total_prompt_tokens,
                            SUM(completion_tokens) as total_completion_tokens
                        FROM markom_audit_log
                        """
                    )
                    row = cursor.fetchone()
                    if row:
                        columns = [desc[0] for desc in cursor.description]
                        return dict(zip(columns, row))
            except Exception as e:
                logger.error("Failed to query audit stats: %s", e)

        total = len(_audit_store)
        successes = sum(1 for r in _audit_store if r["status"] == "success")
        failures = total - successes
        avg_latency = (
            sum(r["latency_ms"] for r in _audit_store) / total if total > 0 else 0
        )
        total_cost = sum(r["cost_usd"] for r in _audit_store)
        total_prompt = sum(r["prompt_tokens"] for r in _audit_store)
        total_completion = sum(r["completion_tokens"] for r in _audit_store)

        return {
            "total_requests": total,
            "successes": successes,
            "failures": failures,
            "avg_latency_ms": round(avg_latency, 2),
            "total_cost_usd": round(total_cost, 6),
            "total_prompt_tokens": total_prompt,
            "total_completion_tokens": total_completion,
        }

    @staticmethod
    def purge_old_records(retention_days: int = 90) -> int:
        pool = _get_db_pool()
        if pool is not None:
            try:
                cutoff = time.time() - (retention_days * 86400)
                with pool.connection() as conn:
                    cursor = conn.execute(
                        "DELETE FROM markom_audit_log WHERE timestamp < to_timestamp(%s)",
                        (cutoff,),
                    )
                    deleted = cursor.rowcount
                    conn.commit()
                    return deleted
            except Exception as e:
                logger.error("Failed to purge old audit records: %s", e)
        return 0


audit_logger_instance = MarkomAuditLogger()
