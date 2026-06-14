from __future__ import annotations

from typing import Any

from src.app.db import get_connection
from src.app.services.observability.trace_schema import (
    SPAN_TYPE_LLM_CALL,
    SPAN_TYPE_MCP_CALL,
    SPAN_TYPE_TOOL_CALL,
)


class ObservabilityMetrics:
    """基础 LLMOps 指标统计。"""

    def summary(self) -> dict[str, Any]:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        COUNT(*) AS span_count,
                        COUNT(*) FILTER (WHERE status = 'error') AS error_count,
                        COUNT(*) FILTER (WHERE span_type = %(llm_span_type)s) AS llm_call_count,
                        COUNT(*) FILTER (WHERE span_type = %(tool_span_type)s) AS tool_call_count,
                        COUNT(*) FILTER (WHERE span_type = %(mcp_span_type)s) AS mcp_call_count,
                        AVG(latency_ms) AS avg_latency_ms,
                        MAX(latency_ms) AS max_latency_ms
                    FROM trace_spans
                    WHERE started_at >= NOW() - INTERVAL '7 days'
                    """,
                    {
                        "llm_span_type": SPAN_TYPE_LLM_CALL.value,
                        "tool_span_type": SPAN_TYPE_TOOL_CALL.value,
                        "mcp_span_type": SPAN_TYPE_MCP_CALL.value,
                    },
                )
                row = cur.fetchone()

        return dict(row or {})
