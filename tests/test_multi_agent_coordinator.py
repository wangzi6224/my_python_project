from unittest.mock import MagicMock

from src.app.services.multi_agent.coordinator.loop import MultiAgentCoordinatorLoop
from src.app.services.multi_agent.coordinator.decision_parser import (
    CoordinatorDecisionParser,
)
from src.app.services.multi_agent.coordinator.planner import CoordinatorPlanner
from src.app.services.multi_agent.coordinator.schemas import (
    CoordinatorDecision,
    CoordinatorGlobalState,
    CoordinatorRound,
)
from src.app.services.multi_agent.schemas import RoleRunResult


def test_run_role_uses_autonomous_role_entrypoint() -> None:
    loop = MultiAgentCoordinatorLoop.__new__(MultiAgentCoordinatorLoop)
    research = MagicMock()
    research.run_autonomous_with_timing.return_value = RoleRunResult(
        role="research",
        status="completed",
    )
    loop.research = research
    loop.coding = MagicMock()
    loop.review = MagicMock()

    state = CoordinatorGlobalState(
        multi_agent_run_id="multi-run-1",
        conversation_id="conversation-1",
        user_message_id="message-1",
        question="分析项目资料",
        rounds=[
            CoordinatorRound(
                round_index=1,
                decision=CoordinatorDecision(
                    type="run_role",
                    role="research",
                    reason="先收集事实",
                    task_objective="检索并整理项目资料",
                ),
                status="running",
            )
        ],
    )

    result = loop._run_role(
        global_state=state,
        round_index=1,
        enable_mcp_tools=True,
    )

    assert result.status == "completed"
    research.run_autonomous_with_timing.assert_called_once()
    research.run_with_timing.assert_not_called()
    role_state = research.run_autonomous_with_timing.call_args.kwargs["role_state"]
    assert role_state.role == "research"
    assert role_state.task_objective == "检索并整理项目资料"


def test_coordinator_rejects_false_same_role_limit() -> None:
    state = CoordinatorGlobalState(
        multi_agent_run_id="multi-run-1",
        conversation_id="conversation-1",
        user_message_id="message-1",
        question="分析项目资料",
        max_same_role_runs=3,
        role_runs=[
            {"role": "research", "status": "completed"},
            {"role": "research", "status": "completed"},
        ],
    )
    decision = CoordinatorDecision(
        type="fail",
        reason="Research 已达到运行上限",
        failure_code="max_same_role_runs",
        failure_message="Research 2 > 1，无法继续",
    )

    try:
        CoordinatorPlanner.__new__(CoordinatorPlanner)._validate_state_transition(
            state,
            decision,
        )
    except ValueError as exc:
        assert "false max_same_role_runs" in str(exc)
    else:
        raise AssertionError("false max_same_role_runs should be rejected")


def test_final_ignores_irrelevant_string_review_feedback() -> None:
    decision = CoordinatorDecisionParser().parse(
        """{
          "type": "final",
          "reason": "Research、Coding、Review 产物已经齐备",
          "review_feedback": "审查已通过，可以汇总"
        }"""
    )

    assert decision.type == "final"
    assert decision.review_feedback is None


def test_revision_wraps_string_review_feedback() -> None:
    decision = CoordinatorDecisionParser().parse(
        """{
          "type": "revise_role",
          "role": "coding",
          "reason": "根据审查意见返工",
          "task_objective": "修复方案遗漏",
          "revision_of_artifact_id": "artifact-coding",
          "review_feedback": "补充测试与风险说明"
        }"""
    )

    assert decision.review_feedback == {"summary": "补充测试与风险说明"}
