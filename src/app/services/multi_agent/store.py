from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from src.app.db import get_connection


def _json(value: Any) -> str:
    return json.dumps(value or {}, ensure_ascii=False)


class MultiAgentStore:
    def create_run(
        self,
        *,
        conversation_id: str,
        assistant_run_id: str | None,
        user_message_id: str,
        input_text: str,
        model: str | None,
        provider: str | None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        run_id = f"multi_agent_run_{uuid4().hex}"

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO multi_agent_runs (
                        id,
                        conversation_id,
                        assistant_run_id,
                        user_message_id,
                        status,
                        input,
                        model,
                        provider,
                        metadata
                    ) VALUES (
                        %(id)s,
                        %(conversation_id)s,
                        %(assistant_run_id)s,
                        %(user_message_id)s,
                        'running',
                        %(input)s,
                        %(model)s,
                        %(provider)s,
                        %(metadata)s::jsonb
                    )
                    RETURNING *
                    """,
                    {
                        "id": run_id,
                        "conversation_id": conversation_id,
                        "assistant_run_id": assistant_run_id,
                        "user_message_id": user_message_id,
                        "input": input_text,
                        "model": model,
                        "provider": provider,
                        "metadata": _json(metadata or {}),
                    },
                )
                row = cur.fetchone()
                conn.commit()
                return dict(row)

    def update_run(
        self,
        run_id: str,
        *,
        status: str,
        final_answer: str | None = None,
        assistant_message_id: str | None = None,
        supervisor_plan: dict[str, Any] | None = None,
        enabled_roles: list[str] | None = None,
        finish_reason: str | None = None,
        latency_ms: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE multi_agent_runs
                    SET
                        status = %(status)s,
                        final_answer = COALESCE(%(final_answer)s, final_answer),
                        assistant_message_id = COALESCE(%(assistant_message_id)s, assistant_message_id),
                        supervisor_plan = COALESCE(%(supervisor_plan)s::jsonb, supervisor_plan),
                        enabled_roles = COALESCE(%(enabled_roles)s::jsonb, enabled_roles),
                        finish_reason = COALESCE(%(finish_reason)s, finish_reason),
                        latency_ms = COALESCE(%(latency_ms)s, latency_ms),
                        metadata = metadata || COALESCE(%(metadata)s::jsonb, '{}'::jsonb),
                        updated_at = NOW()
                    WHERE id = %(id)s
                    """,
                    {
                        "id": run_id,
                        "status": status,
                        "final_answer": final_answer,
                        "assistant_message_id": assistant_message_id,
                        "supervisor_plan": (
                            _json(supervisor_plan)
                            if supervisor_plan is not None
                            else None
                        ),
                        "enabled_roles": (
                            json.dumps(enabled_roles, ensure_ascii=False)
                            if enabled_roles is not None
                            else None
                        ),
                        "finish_reason": finish_reason,
                        "latency_ms": latency_ms,
                        "metadata": _json(metadata) if metadata is not None else None,
                    },
                )
                conn.commit()

    def create_coordinator_round(
        self,
        round_item: Any,
        *,
        multi_agent_run_id: str,
    ) -> str:
        round_id = f"multi_agent_coordinator_round_{uuid4().hex}"
        data = round_item.model_dump(mode="json")
        decision = data["decision"]

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO multi_agent_coordinator_rounds (
                        id,
                        multi_agent_run_id,
                        round_index,
                        decision_type,
                        decision,
                        status,
                        role,
                        role_run_id,
                        artifact_id,
                        handoff_id,
                        latency_ms,
                        error_code,
                        error_message,
                        metadata
                    ) VALUES (
                        %(id)s,
                        %(multi_agent_run_id)s,
                        %(round_index)s,
                        %(decision_type)s,
                        %(decision)s::jsonb,
                        %(status)s,
                        %(role)s,
                        %(role_run_id)s,
                        %(artifact_id)s,
                        %(handoff_id)s,
                        %(latency_ms)s,
                        %(error_code)s,
                        %(error_message)s,
                        %(metadata)s::jsonb
                    )
                    """,
                    {
                        "id": round_id,
                        "multi_agent_run_id": multi_agent_run_id,
                        "round_index": data["round_index"],
                        "decision_type": decision["type"],
                        "decision": _json(decision),
                        "status": data["status"],
                        "role": decision.get("role") or decision.get("target_role"),
                        "role_run_id": data.get("role_run_id"),
                        "artifact_id": data.get("artifact_id"),
                        "handoff_id": data.get("handoff_id"),
                        "latency_ms": data.get("latency_ms"),
                        "error_code": data.get("error_code"),
                        "error_message": data.get("error_message"),
                        "metadata": _json(data.get("metadata") or {}),
                    },
                )
                conn.commit()

        return round_id

    def update_coordinator_round(
        self,
        round_id: str,
        round_item: Any,
    ) -> None:
        data = round_item.model_dump(mode="json")
        decision = data["decision"]

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE multi_agent_coordinator_rounds
                    SET
                        decision_type = %(decision_type)s,
                        decision = %(decision)s::jsonb,
                        status = %(status)s,
                        role = %(role)s,
                        role_run_id = %(role_run_id)s,
                        artifact_id = %(artifact_id)s,
                        handoff_id = %(handoff_id)s,
                        latency_ms = %(latency_ms)s,
                        error_code = %(error_code)s,
                        error_message = %(error_message)s,
                        metadata = %(metadata)s::jsonb,
                        updated_at = NOW()
                    WHERE id = %(id)s
                    """,
                    {
                        "id": round_id,
                        "decision_type": decision["type"],
                        "decision": _json(decision),
                        "status": data["status"],
                        "role": decision.get("role") or decision.get("target_role"),
                        "role_run_id": data.get("role_run_id"),
                        "artifact_id": data.get("artifact_id"),
                        "handoff_id": data.get("handoff_id"),
                        "latency_ms": data.get("latency_ms"),
                        "error_code": data.get("error_code"),
                        "error_message": data.get("error_message"),
                        "metadata": _json(data.get("metadata") or {}),
                    },
                )
                conn.commit()

    def create_artifact(self, artifact: Any, *, multi_agent_run_id: str) -> None:
        data = artifact.model_dump(mode="json")
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO multi_agent_artifacts (
                        id,
                        multi_agent_run_id,
                        role,
                        artifact_type,
                        title,
                        content,
                        data,
                        source_refs,
                        confidence,
                        metadata
                    ) VALUES (
                        %(id)s,
                        %(multi_agent_run_id)s,
                        %(role)s,
                        %(artifact_type)s,
                        %(title)s,
                        %(content)s,
                        %(data)s::jsonb,
                        %(source_refs)s::jsonb,
                        %(confidence)s,
                        %(metadata)s::jsonb
                    )
                    """,
                    {
                        "id": artifact.id,
                        "multi_agent_run_id": multi_agent_run_id,
                        "role": artifact.role,
                        "artifact_type": artifact.artifact_type,
                        "title": artifact.title,
                        "content": artifact.content,
                        "data": _json(data.get("data") or {}),
                        "source_refs": json.dumps(
                            data.get("source_refs") or [], ensure_ascii=False
                        ),
                        "confidence": artifact.confidence,
                        "metadata": _json(data.get("metadata") or {}),
                    },
                )
                conn.commit()

    def create_handoff(self, handoff: Any, *, multi_agent_run_id: str) -> None:
        data = handoff.model_dump(mode="json")
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO multi_agent_handoffs (
                        id,
                        multi_agent_run_id,
                        from_role,
                        to_role,
                        task_id,
                        summary,
                        payload,
                        confidence
                    ) VALUES (
                        %(id)s,
                        %(multi_agent_run_id)s,
                        %(from_role)s,
                        %(to_role)s,
                        %(task_id)s,
                        %(summary)s,
                        %(payload)s::jsonb,
                        %(confidence)s
                    )
                    """,
                    {
                        "id": handoff.id,
                        "multi_agent_run_id": multi_agent_run_id,
                        "from_role": handoff.from_role,
                        "to_role": handoff.to_role,
                        "task_id": handoff.task_id,
                        "summary": handoff.summary,
                        "payload": _json(data.get("payload") or {}),
                        "confidence": handoff.confidence,
                    },
                )
                conn.commit()
