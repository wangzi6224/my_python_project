from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

from src.app.services.observability.trace_schema import SpanType
from src.app.services.observability.trace_schema import TraceSpan
from src.app.services.observability.trace_schema import TraceSpanCreate
from src.app.services.observability.trace_store import TraceStore


class TraceSpanContext:
    """TraceSpan 的创建、输出、错误一起处理了"""

    def __init__(self, *, span: TraceSpan, store: TraceStore) -> None:
        self.span = span
        self.id = span.id
        self._store = store
        self._finished = False
        self._status = "success"
        self._output: dict[str, Any] | None = None
        self._metadata: dict[str, Any] | None = None

    def set_result(
        self,
        *,
        status: str = "success",
        output: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self._status = status
        self._output = output
        self._metadata = metadata

    def finish(
        self,
        *,
        status: str = "success",
        output: dict[str, Any] | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TraceSpan:
        self._finished = True
        return self._store.finish_span(
            self.id,
            status=status,
            output=output,
            error_code=error_code,
            error_message=error_message,
            metadata=metadata,
        )


@contextmanager
def trace_span(
    *,
    trace_id: str,
    run_id: str,
    span_type: SpanType,
    name: str,
    parent_span_id: str | None = None,
    conversation_id: str | None = None,
    assistant_run_id: str | None = None,
    agent_run_id: str | None = None,
    input: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    store: TraceStore | None = None,
) -> Iterator[TraceSpanContext]:
    """创建并自动结束一个 TraceSpan。"""

    trace_store = store or TraceStore()

    span = trace_store.create_span(
        TraceSpanCreate(
            trace_id=trace_id,
            parent_span_id=parent_span_id,
            run_id=run_id,
            conversation_id=conversation_id,
            assistant_run_id=assistant_run_id,
            agent_run_id=agent_run_id,
            span_type=span_type,
            name=name,
            input=input or {},
            metadata=metadata or {},
        )
    )
    scope = TraceSpanContext(span=span, store=trace_store)

    try:
        yield scope
        if not scope._finished:
            trace_store.finish_span(
                span.id,
                status=scope._status,
                output=scope._output,
                metadata=scope._metadata,
            )
    except Exception as exc:
        if not scope._finished:
            trace_store.finish_span(
                span.id,
                status="error",
                error_code=exc.__class__.__name__,
                error_message=str(exc),
            )
        raise
