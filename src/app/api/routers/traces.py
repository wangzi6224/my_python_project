from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from src.app.services.assistant.run_store import AssistantRunStore
from src.app.services.observability.metrics import ObservabilityMetrics
from src.app.services.observability.trace_store import TraceStore

router = APIRouter(prefix="/traces", tags=["traces"])


@router.get("")
def list_traces(conversation_id: str) -> dict[str, Any]:
    runs = AssistantRunStore().list_runs_by_conversation(conversation_id)
    items: list[dict[str, Any]] = []

    for run in runs:
        metadata = run.get("metadata") or {}
        trace_id = metadata.get("trace_id") or f"trace_{run['id']}"
        trace = run.get("trace") or {}
        multi_agent = trace.get("multi_agent") or {}
        summary = metadata.get("trace_summary") or {}
        items.append(
            {
                "trace_id": trace_id,
                "assistant_run_id": run["id"],
                "conversation_id": run.get("conversation_id"),
                "mode": run.get("mode"),
                "status": run.get("status"),
                "input": run.get("input"),
                "final_answer": run.get("final_answer"),
                "model": run.get("model"),
                "provider": run.get("provider"),
                "latency_ms": run.get("latency_ms"),
                "created_at": run.get("created_at"),
                "updated_at": run.get("updated_at"),
                "summary": summary,
                "multi_agent": {
                    "enabled": bool(multi_agent.get("enabled")),
                    "run_id": multi_agent.get("run_id"),
                    "roles_used": multi_agent.get("roles_used") or [],
                    "artifact_count": multi_agent.get("artifact_count") or 0,
                    "handoff_count": multi_agent.get("handoff_count") or 0,
                    "review_decision": multi_agent.get("review_decision"),
                    "finish_reason": (multi_agent.get("coordinator") or {}).get(
                        "finish_reason"
                    ),
                    "round_count": len(
                        (multi_agent.get("coordinator") or {}).get("rounds") or []
                    ),
                },
            }
        )

    return {"conversation_id": conversation_id, "items": items}


@router.get("/{trace_id}")
def get_trace(trace_id: str) -> dict[str, Any]:
    store = TraceStore()
    spans = store.list_spans(trace_id)

    if not spans:
        raise HTTPException(
            status_code=404,
            detail=f"Trace 不存在: {trace_id}",
        )

    assistant_run_id = next(
        (span.assistant_run_id for span in spans if span.assistant_run_id),
        None,
    )
    run = AssistantRunStore().get_run(assistant_run_id) if assistant_run_id else None

    return {
        "trace_id": trace_id,
        "summary": store.summarize_trace(trace_id),
        "spans": [span.model_dump(mode="json") for span in spans],
        "run": run,
    }


@router.get("/{trace_id}/summary")
def get_trace_summary(trace_id: str) -> dict[str, Any]:
    return TraceStore().summarize_trace(trace_id)


@router.get("/metrics/observability")
def get_observability_metrics() -> dict[str, Any]:
    return ObservabilityMetrics().summary()
