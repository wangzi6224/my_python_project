from __future__ import annotations

from datetime import datetime
from typing import Any, cast
from uuid import uuid4

from psycopg.types.json import Jsonb

from src.app.db import get_connection
from src.app.services.observability.redaction import redact_dict
from src.app.services.observability.trace_schema import (
    SPAN_TYPE_LLM_CALL,
    SPAN_TYPE_MCP_CALL,
    SPAN_TYPE_TOOL_CALL,
    TraceSpan,
    TraceSpanCreate,
)


def _normalize_span(row: dict[str, Any]) -> TraceSpan:
    data = dict(row)

    for key in ("started_at", "ended_at"):
        if isinstance(data.get(key), datetime):
            data[key] = data[key].isoformat()

    data["metadata"] = data.get("metadata") or {}
    return TraceSpan(**data)


class TraceStore:
    """TraceSpan 数据库存储。"""

    def create_span(self, payload: TraceSpanCreate) -> TraceSpan:
        span_id = f"span_{uuid4().hex}"

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO trace_spans (
                        id,
                        trace_id,
                        parent_span_id,
                        run_id,
                        conversation_id,
                        assistant_run_id,
                        agent_run_id,
                        span_type,
                        name,
                        status,
                        input,
                        metadata,
                        started_at
                    ) VALUES (
                        %(id)s,
                        %(trace_id)s,
                        %(parent_span_id)s,
                        %(run_id)s,
                        %(conversation_id)s,
                        %(assistant_run_id)s,
                        %(agent_run_id)s,
                        %(span_type)s,
                        %(name)s,
                        'running',
                        %(input)s::jsonb,
                        %(metadata)s::jsonb,
                        NOW()
                    )
                    RETURNING *
                    """,
                    {
                        "id": span_id,
                        "trace_id": payload.trace_id,
                        "parent_span_id": payload.parent_span_id,
                        "run_id": payload.run_id,
                        "conversation_id": payload.conversation_id,
                        "assistant_run_id": payload.assistant_run_id,
                        "agent_run_id": payload.agent_run_id,
                        "span_type": payload.span_type.value,
                        "name": payload.name,
                        "input": Jsonb(
                            redact_dict(payload.input or {}, max_text_chars=2000)
                        ),
                        "metadata": Jsonb(
                            redact_dict(payload.metadata, max_text_chars=2000)
                        ),
                    },
                )
                row = cur.fetchone()
                conn.commit()

        return _normalize_span(cast(dict[str, Any], row))

    def finish_span(
        self,
        span_id: str,
        *,
        status: str = "success",
        output: dict[str, Any] | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TraceSpan:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE trace_spans
                    SET
                        status = %(status)s,
                        output = %(output)s::jsonb,
                        error_code = %(error_code)s,
                        error_message = %(error_message)s,
                        metadata = metadata || %(metadata)s::jsonb,
                        ended_at = NOW(),
                        latency_ms = EXTRACT(
                            EPOCH FROM (NOW() - started_at)
                        )::float * 1000
                    WHERE id = %(span_id)s
                    RETURNING *
                    """,
                    {
                        "span_id": span_id,
                        "status": status,
                        "output": Jsonb(redact_dict(output or {}, max_text_chars=3000)),
                        "error_code": error_code,
                        "error_message": error_message,
                        "metadata": Jsonb(
                            redact_dict(metadata or {}, max_text_chars=2000)
                        ),
                    },
                )
                row = cur.fetchone()
                conn.commit()

        return _normalize_span(cast(dict[str, Any], row))

    def list_spans(self, trace_id: str) -> list[TraceSpan]:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT *
                    FROM trace_spans
                    WHERE trace_id = %(trace_id)s
                    ORDER BY started_at ASC
                    """,
                    {"trace_id": trace_id},
                )
                rows = cur.fetchall()

        return [_normalize_span(cast(dict[str, Any], row)) for row in rows]

    def summarize_trace(self, trace_id: str) -> dict[str, Any]:
        spans = self.list_spans(trace_id)

        total_latency = max(
            [span.latency_ms or 0 for span in spans],
            default=0,
        )

        error_count = sum(1 for span in spans if span.status == "error")

        llm_spans = [span for span in spans if span.span_type == SPAN_TYPE_LLM_CALL]
        tool_spans = [span for span in spans if span.span_type == SPAN_TYPE_TOOL_CALL]
        mcp_spans = [span for span in spans if span.span_type == SPAN_TYPE_MCP_CALL]

        total_tokens = 0
        estimated_cost = 0.0

        for span in llm_spans:
            usage = span.metadata.get("usage") or {}
            cost = span.metadata.get("cost") or {}

            total_tokens += int(usage.get("total_tokens") or 0)
            estimated_cost += float(cost.get("total_cost") or 0)

        return {
            "trace_id": trace_id,
            "span_count": len(spans),
            "error_count": error_count,
            "llm_call_count": len(llm_spans),
            "tool_call_count": len(tool_spans),
            "mcp_call_count": len(mcp_spans),
            "total_latency_ms": total_latency,
            "total_tokens": total_tokens,
            "estimated_cost": estimated_cost,
        }
