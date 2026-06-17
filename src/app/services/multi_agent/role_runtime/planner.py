from __future__ import annotations

from time import perf_counter

from jsonschema import ValidationError

from src.app.config import resolve_llm_model
from src.app.services.llm.factory import get_llm_provider
from src.app.services.multi_agent.role_runtime.decision_parser import RoleDecisionParser
from src.app.services.multi_agent.role_runtime.prompt_builder import (
    ROLE_PLANNER_PROMPT_VERSION,
    RolePlannerPromptBuilder,
)
from src.app.services.multi_agent.role_runtime.schemas import (
    AutonomousRoleState,
    RolePlannerDecision,
)
from src.app.services.tools.registry import ToolRegistry


class RolePlanner:
    def __init__(self, *, tool_registry: ToolRegistry) -> None:
        self.tool_registry = tool_registry
        self.llm_provider = get_llm_provider()
        self.prompt_builder = RolePlannerPromptBuilder()
        self.parser = RoleDecisionParser()

    def plan(self, state: AutonomousRoleState) -> RolePlannerDecision:
        start = perf_counter()
        raw_content: str | None = None
        messages = self.prompt_builder.build_messages(
            state=state,
            tools=self.tool_registry.list_tools(),
        )
        model = resolve_llm_model(model=state.model)

        try:
            response = self.llm_provider.structured_chat(
                messages=messages,
                model=model,
                thinking_enabled=False,
            )
            raw_content = response.content
            decision = self.parser.parse(response.content)
            decision = self._validate_decision(state, decision)

            state.planner_decision_count += 1
            state.metadata.setdefault("role_planner_events", []).append(
                {
                    "planner": "role_llm",
                    "prompt_version": ROLE_PLANNER_PROMPT_VERSION,
                    "model": response.model,
                    "provider": response.provider,
                    "latency_ms": int((perf_counter() - start) * 1000),
                    "decision": decision.model_dump(mode="json"),
                }
            )
            return decision

        except Exception as exc:
            state.planner_fallback_count += 1
            state.metadata.setdefault("role_planner_events", []).append(
                {
                    "planner": "role_llm",
                    "fallback": True,
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                    "raw_content": raw_content[:4000] if raw_content else None,
                    "latency_ms": int((perf_counter() - start) * 1000),
                    "fallback_decision": self._fallback_decision(state).model_dump(
                        mode="json"
                    ),
                }
            )
            return self._fallback_decision(state)

    def _validate_decision(
        self,
        state: AutonomousRoleState,
        decision: RolePlannerDecision,
    ) -> RolePlannerDecision:
        if decision.type == "final":
            return decision

        assert decision.tool_name is not None

        self.tool_registry.get(decision.tool_name)

        try:
            self.tool_registry.validate_arguments(
                decision.tool_name,
                decision.arguments,
            )
        except ValidationError as exc:
            raise ValueError(
                f"Invalid tool arguments: {exc.message}"
            ) from exc

        for step in state.steps:
            if step.type != "tool_call":
                continue
            if step.tool_name == decision.tool_name and step.arguments == decision.arguments:
                raise ValueError("Duplicate role tool call")

        return decision

    def _fallback_final(self, state: AutonomousRoleState) -> RolePlannerDecision:
        return RolePlannerDecision(
            type="final",
            reason="RolePlanner 失败，使用保守 fallback 结束当前角色。",
            confidence=0.35,
            artifact_title=f"{state.role} fallback artifact",
            artifact_content=(
                f"{state.role} 未能完成完整自主规划。\n\n"
                f"任务：{state.task_objective}\n\n"
                f"已有观察：{[obs.model_dump(mode='json') for obs in state.observations]}\n\n"
                "最终回答应说明该角色结果可能不完整。"
            ),
            artifact_data={
                "fallback": True,
                "observation_count": len(state.observations),
            },
            open_questions=["RolePlanner 输出解析或校验失败"],
        )

    def _fallback_decision(
        self,
        state: AutonomousRoleState,
    ) -> RolePlannerDecision:
        """Research 首次规划失败时仍先获取事实，避免直接生成空产物。"""
        available_tools = {
            item.get("name") for item in self.tool_registry.list_tools()
        }
        has_search_observation = any(
            item.tool_name == "search_docs" for item in state.observations
        )

        if (
            state.role == "research"
            and "search_docs" in available_tools
            and not has_search_observation
        ):
            return RolePlannerDecision(
                type="tool_call",
                reason=(
                    "RolePlanner 输出无法解析，使用 Research 安全 fallback "
                    "检索项目知识库。"
                ),
                confidence=0.45,
                tool_name="search_docs",
                arguments={
                    "query": state.task_objective or state.question,
                    "top_k": 5,
                    "score_threshold": 0.3,
                },
            )

        return self._fallback_final(state)
