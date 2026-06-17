from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, cast

from src.app.db import get_connection
from src.app.exceptions import ConversationError


def _normalize_run(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None

    result = dict(row)

    for key in ["created_at", "updated_at"]:
        if isinstance(result.get(key), datetime):
            result[key] = result[key].isoformat()

    result["trace"] = result.get("trace") or {}
    result["metadata"] = result.get("metadata") or {}

    return result


class AssistantRunStore:
    def list_runs_by_conversation(self, conversation_id: str) -> list[dict[str, Any]]:
        """按时间倒序返回会话的 Assistant Run，供统一 Trace 列表使用。"""
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT *
                    FROM assistant_runs
                    WHERE conversation_id = %(conversation_id)s
                    ORDER BY created_at DESC
                    """,
                    {"conversation_id": conversation_id},
                )
                rows = cur.fetchall()

        return [
            cast(dict[str, Any], _normalize_run(cast(dict[str, Any], row)))
            for row in rows
        ]

    def create_run(
        self,
        *,
        conversation_id: str,
        mode: str,
        input_text: str,
        model: str | None = None,
        provider: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        run_id = str(uuid.uuid4())

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO assistant_runs (
                        id,
                        conversation_id,
                        mode,
                        status,
                        input,
                        model,
                        provider,
                        metadata,
                        created_at,
                        updated_at
                    )
                    VALUES (
                        %(id)s,
                        %(conversation_id)s,
                        %(mode)s,
                        'running',
                        %(input)s,
                        %(model)s,
                        %(provider)s,
                        %(metadata)s::jsonb,
                        NOW(),
                        NOW()
                    )
                    RETURNING *
                    """,
                    {
                        "id": run_id,
                        "conversation_id": conversation_id,
                        "mode": mode,
                        "input": input_text,
                        "model": model,
                        "provider": provider,
                        "metadata": json.dumps(metadata or {}, ensure_ascii=False),
                    },
                )
                row = cur.fetchone()

            conn.commit()

        run = _normalize_run(cast(dict[str, Any] | None, row))

        if run is None:
            raise ConversationError(
                message="创建 Assistant Run 失败",
                status_code=500,
            )

        return run

    def update_run(
        self,
        run_id: str,
        *,
        status: str,
        mode: str | None = None,
        user_message_id: str | None = None,
        assistant_message_id: str | None = None,
        final_answer: str | None = None,
        model: str | None = None,
        provider: str | None = None,
        latency_ms: int | None = None,
        trace: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE assistant_runs
                    SET
                        status = %(status)s,
                        mode = COALESCE(%(mode)s, mode),
                        user_message_id = COALESCE(%(user_message_id)s, user_message_id),
                        assistant_message_id = COALESCE(%(assistant_message_id)s, assistant_message_id),
                        final_answer = COALESCE(%(final_answer)s, final_answer),
                        model = COALESCE(%(model)s, model),
                        provider = COALESCE(%(provider)s, provider),
                        latency_ms = COALESCE(%(latency_ms)s, latency_ms),
                        trace = COALESCE(%(trace)s::jsonb, trace),
                        metadata = COALESCE(%(metadata)s::jsonb, metadata),
                        updated_at = NOW()
                    WHERE id = %(run_id)s
                    RETURNING *
                    """,
                    {
                        "run_id": run_id,
                        "status": status,
                        "mode": mode,
                        "user_message_id": user_message_id,
                        "assistant_message_id": assistant_message_id,
                        "final_answer": final_answer,
                        "model": model,
                        "provider": provider,
                        "latency_ms": latency_ms,
                        "trace": (
                            json.dumps(trace, ensure_ascii=False)
                            if trace is not None
                            else None
                        ),
                        "metadata": (
                            json.dumps(metadata, ensure_ascii=False)
                            if metadata is not None
                            else None
                        ),
                    },
                )
                row = cur.fetchone()

            conn.commit()

        run = _normalize_run(cast(dict[str, Any] | None, row))

        if run is None:
            raise ConversationError(
                message="Assistant Run 不存在",
                detail=f"run_id={run_id}",
                status_code=404,
            )

        return run

    def get_run(self, run_id: str) -> dict[str, Any]:
        """查询单条 AssistantRun。run 不存在时抛 404 ConversationError。"""
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT *
                    FROM assistant_runs
                    WHERE id = %(run_id)s
                    """,
                    {"run_id": run_id},
                )
                row = cur.fetchone()

        run = _normalize_run(cast(dict[str, Any] | None, row))

        if run is None:
            raise ConversationError(
                message="Assistant Run 不存在",
                detail=f"run_id={run_id}",
                status_code=404,
            )

        return run
