from unittest.mock import MagicMock

from src.app.services.multi_agent.role_runtime.planner import RolePlanner
from src.app.services.multi_agent.role_runtime.schemas import (
    AutonomousRoleState,
    RoleObservation,
)


def _research_state() -> AutonomousRoleState:
    return AutonomousRoleState(
        multi_agent_run_id="multi-run-1",
        coordinator_round_index=1,
        role="research",
        conversation_id="conversation-1",
        user_message_id="message-1",
        question="NexusAI 的 Multi-Agent 如何工作？",
        task_objective="检索 Multi-Agent 的项目事实",
    )


def test_research_parse_fallback_searches_before_final() -> None:
    registry = MagicMock()
    registry.list_tools.return_value = [{"name": "search_docs"}]
    planner = RolePlanner.__new__(RolePlanner)
    planner.tool_registry = registry

    decision = planner._fallback_decision(_research_state())

    assert decision.type == "tool_call"
    assert decision.tool_name == "search_docs"
    assert decision.arguments["query"] == "检索 Multi-Agent 的项目事实"


def test_research_parse_fallback_finishes_after_search_observation() -> None:
    registry = MagicMock()
    registry.list_tools.return_value = [{"name": "search_docs"}]
    planner = RolePlanner.__new__(RolePlanner)
    planner.tool_registry = registry
    state = _research_state()
    state.observations.append(
        RoleObservation(
            step=1,
            tool_name="search_docs",
            arguments={"query": state.question},
            success=True,
            result={"data": {"items": [{"content": "项目事实"}]}},
        )
    )

    decision = planner._fallback_decision(state)

    assert decision.type == "final"
    assert "项目事实" in (decision.artifact_content or "")
