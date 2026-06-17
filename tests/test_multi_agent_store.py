from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from src.app.services.multi_agent.coordinator.schemas import (
    CoordinatorDecision,
    CoordinatorRound,
)
from src.app.services.multi_agent.store import MultiAgentStore


def _mock_connection() -> tuple[MagicMock, MagicMock]:
    cursor = MagicMock()
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.cursor.return_value.__enter__.return_value = cursor
    return connection, cursor


def test_create_coordinator_round_maps_database_fields() -> None:
    connection, cursor = _mock_connection()
    round_item = CoordinatorRound(
        round_index=2,
        decision=CoordinatorDecision(
            type="run_role",
            reason="需要实现功能",
            role="coding",
        ),
        status="running",
        metadata={"trace_id": "trace-1"},
    )

    with patch(
        "src.app.services.multi_agent.store.get_connection",
        return_value=connection,
    ):
        round_id = MultiAgentStore().create_coordinator_round(
            round_item,
            multi_agent_run_id="run-1",
        )

    params = cursor.execute.call_args.args[1]
    assert round_id.startswith("multi_agent_coordinator_round_")
    assert params["id"] == round_id
    assert params["multi_agent_run_id"] == "run-1"
    assert params["round_index"] == 2
    assert params["decision_type"] == "run_role"
    assert params["role"] == "coding"
    assert json.loads(params["decision"])["reason"] == "需要实现功能"
    assert json.loads(params["metadata"]) == {"trace_id": "trace-1"}
    connection.commit.assert_called_once_with()


def test_update_coordinator_round_syncs_result_fields() -> None:
    connection, cursor = _mock_connection()
    round_item = CoordinatorRound(
        round_index=2,
        decision=CoordinatorDecision(
            type="request_review",
            reason="检查实现",
            role="review",
        ),
        status="completed",
        role_run_id="role-run-1",
        artifact_id="artifact-1",
        handoff_id="handoff-1",
        latency_ms=125,
        metadata={"attempt": 1},
    )

    with patch(
        "src.app.services.multi_agent.store.get_connection",
        return_value=connection,
    ):
        MultiAgentStore().update_coordinator_round("round-1", round_item)

    sql, params = cursor.execute.call_args.args
    assert "updated_at = NOW()" in sql
    assert params["id"] == "round-1"
    assert params["decision_type"] == "request_review"
    assert params["role"] == "review"
    assert params["status"] == "completed"
    assert params["role_run_id"] == "role-run-1"
    assert params["artifact_id"] == "artifact-1"
    assert params["handoff_id"] == "handoff-1"
    assert params["latency_ms"] == 125
    assert json.loads(params["metadata"]) == {"attempt": 1}
    connection.commit.assert_called_once_with()
