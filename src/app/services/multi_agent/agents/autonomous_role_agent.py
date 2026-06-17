from __future__ import annotations

from time import perf_counter
from typing import Any
from uuid import uuid4

from src.app.services.multi_agent.agents.base import BaseRoleAgent
from src.app.services.multi_agent.role_runtime.planner import RolePlanner
from src.app.services.multi_agent.role_runtime.schemas import (
    AutonomousRoleState,
    RoleObservation,
    RoleStep,
)
from src.app.services.multi_agent.role_runtime.tool_registry_factory import (
    RoleToolRegistryFactory,
)
from src.app.services.multi_agent.schemas import AgentArtifact, ArtifactType, RoleRunResult
from src.app.services.tools.registry import ToolRegistry
from src.app.services.tools.safety import limit_tool_result


class AutonomousRoleAgent(BaseRoleAgent):
    artifact_type: ArtifactType
    default_artifact_title: str

    def run_autonomous_with_timing(
        self,
        *,
        role_state: AutonomousRoleState,
        enable_mcp_tools: bool,
    ) -> RoleRunResult:
        """执行 Level 3 角色循环，并保持与旧角色入口一致的失败返回语义。"""
        start = perf_counter()
        try:
            result = self.run_autonomous(
                role_state=role_state,
                enable_mcp_tools=enable_mcp_tools,
            )
            result.latency_ms = int((perf_counter() - start) * 1000)
            return result
        except Exception as exc:
            return RoleRunResult(
                role=self.role,
                status="failed",
                latency_ms=int((perf_counter() - start) * 1000),
                error_code=type(exc).__name__,
                error_message=str(exc),
            )

    def run_autonomous(
        self,
        *,
        role_state: AutonomousRoleState,
        enable_mcp_tools: bool,
    ) -> RoleRunResult:
        start = perf_counter()
        registry = RoleToolRegistryFactory().build(
            role=self.role,
            enable_mcp_tools=enable_mcp_tools,
        )
        planner = RolePlanner(tool_registry=registry)

        final_decision = None

        for index in range(role_state.max_steps):
            step_index = index + 1
            decision = planner.plan(role_state)

            if decision.type == "final":
                step = RoleStep(
                    step=step_index,
                    type="final",
                    reason=decision.reason,
                    decision=decision.model_dump(mode="json"),
                    success=True,
                )
                role_state.steps.append(step)
                role_state.finish_reason = "role_planner_final"
                final_decision = decision
                break

            assert decision.tool_name is not None
            step = self._execute_tool_step(
                registry=registry,
                step_index=step_index,
                tool_name=decision.tool_name,
                arguments=decision.arguments,
                reason=decision.reason,
                decision=decision.model_dump(mode="json"),
            )
            role_state.steps.append(step)
            role_state.observations.append(
                RoleObservation(
                    step=step.step,
                    tool_name=step.tool_name or "unknown",
                    arguments=step.arguments,
                    success=step.success,
                    result=step.result,
                    error_code=step.error_code,
                    error_message=step.error_message,
                )
            )

        if final_decision is None:
            role_state.finish_reason = "max_role_steps_reached"
            final_decision = planner._fallback_final(role_state)

        artifact = AgentArtifact(
            id=f"artifact_{uuid4().hex}",
            role=self.role,
            artifact_type=self.artifact_type,
            title=final_decision.artifact_title or self.default_artifact_title,
            content=final_decision.artifact_content or "",
            data={
                **final_decision.artifact_data,
                "open_questions": final_decision.open_questions,
                "finish_reason": role_state.finish_reason,
                "planner_decision_count": role_state.planner_decision_count,
                "planner_fallback_count": role_state.planner_fallback_count,
                "step_count": len(role_state.steps),
            },
            source_refs=[],
            confidence=final_decision.confidence,
            metadata={
                "autonomous": True,
                "prompt_version": self.prompt_version,
                "role_state": role_state.model_dump(mode="json"),
            },
        )

        return RoleRunResult(
            role=self.role,
            status="completed",
            artifact=artifact,
            latency_ms=int((perf_counter() - start) * 1000),
            trace={
                "autonomous": True,
                "steps": [step.model_dump(mode="json") for step in role_state.steps],
                "observations": [
                    obs.model_dump(mode="json") for obs in role_state.observations
                ],
                "role_planner_events": role_state.metadata.get("role_planner_events", []),
                "finish_reason": role_state.finish_reason,
                "tool_calls": self._extract_tool_calls(role_state),
            },
        )

    def _execute_tool_step(
        self,
        *,
        registry: ToolRegistry,
        step_index: int,
        tool_name: str,
        arguments: dict[str, Any],
        reason: str,
        decision: dict[str, Any],
    ) -> RoleStep:
        start = perf_counter()
        try:
            registry.validate_arguments(tool_name, arguments)
            tool = registry.get(tool_name)
            raw_result = tool.run(arguments)
            result = limit_tool_result(raw_result)
            return RoleStep(
                step=step_index,
                type="tool_call",
                tool_name=tool_name,
                arguments=arguments,
                result=result,
                success=bool(result.get("success")),
                latency_ms=int((perf_counter() - start) * 1000),
                reason=reason,
                decision=decision,
            )
        except Exception as exc:
            return RoleStep(
                step=step_index,
                type="error",
                tool_name=tool_name,
                arguments=arguments,
                success=False,
                latency_ms=int((perf_counter() - start) * 1000),
                reason=reason,
                error_code=type(exc).__name__,
                error_message=str(exc),
                decision=decision,
            )

    def _extract_tool_calls(self, role_state: AutonomousRoleState) -> list[dict[str, Any]]:
        calls: list[dict[str, Any]] = []
        for step in role_state.steps:
            if step.type not in ("tool_call", "error") or not step.tool_name:
                continue
            calls.append(
                {
                    "tool_name": step.tool_name,
                    "arguments": step.arguments,
                    "success": step.success,
                    "latency_ms": step.latency_ms,
                    "role": self.role,
                    "source": "internal",
                    "metadata": {
                        "role": self.role,
                        "coordinator_round_index": role_state.coordinator_round_index,
                        "multi_agent_run_id": role_state.multi_agent_run_id,
                        "role_run_id": role_state.role_run_id,
                    },
                    "result": step.result,
                    "error_code": step.error_code,
                    "error_message": step.error_message,
                }
            )
        return calls
