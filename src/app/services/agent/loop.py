from __future__ import annotations

import json
from time import perf_counter
from typing import Any

from jsonschema import ValidationError

from src.app.agent_trace_store import create_agent_event, create_agent_step
from src.app.config import get_agent_tool_timeout_seconds
from src.app.services.agent.state import AgentObservation, AgentState, AgentStep
from src.app.services.agent.planner import RuleBasedPlanner
from src.app.services.agent.llm_planner import LLMPlanner
from src.app.services.assistant.event import (
    EVENT_AGENT_MAX_STEPS_REACHED,
    EVENT_AGENT_STEP_FINAL,
    EVENT_AGENT_STEP_START,
    EVENT_DUPLICATE_TOOL_CALL_BLOCKED,
    EVENT_TOOL_ERROR,
    EVENT_TOOL_RESULT,
)
from src.app.services.observability.redaction import redact_dict
from src.app.services.observability.trace_schema import (
    SPAN_TYPE_TOOL_CALL,
    TraceSpanCreate,
)
from src.app.services.observability.trace_store import TraceStore
from src.app.services.tools.registry import ToolRegistry
from src.app.services.tools.safety import limit_tool_result


# 生成工具调用的唯一键，用于检测重复调用，避免 Agent 陷入循环。
def _tool_call_key(tool_name: str, arguments: dict[str, Any]) -> str:
    return json.dumps(
        {"tool_name": tool_name, "arguments": arguments},
        ensure_ascii=False,
        sort_keys=True,  # 确保参数顺序不同但内容相同的工具调用被识别为重复调用
    )


# 检测是否存在重复工具调用，避免 Agent 陷入循环。
def _has_duplicate_tool_call(
    state: AgentState, tool_name: str, arguments: dict[str, Any]
) -> bool:
    current_key = _tool_call_key(tool_name, arguments)

    for step in state.steps:
        if step.type != "tool_call" or not step.tool_name:
            continue
        if _tool_call_key(step.tool_name, step.arguments) == current_key:
            return True

    return False


# 将 AgentStep 转换为 AgentObservation，供下一轮 planner 使用。
def _build_observation(step: AgentStep) -> AgentObservation:
    return AgentObservation(
        step=step.step,
        tool_name=step.tool_name or "unknown",
        arguments=step.arguments,
        success=step.success,
        result=step.result,
        error_code=step.error_code
        or ((step.result or {}).get("error") or {}).get("code"),
        error_message=step.error_message
        or ((step.result or {}).get("error") or {}).get("message"),
    )


class AgentLoop:
    def __init__(self, tool_registry: ToolRegistry, planner_type: str = "llm") -> None:
        self.tool_registry = tool_registry
        self.trace_store = TraceStore()
        if planner_type == "llm":
            self.planner = LLMPlanner(tool_registry=tool_registry)
        else:
            self.planner = RuleBasedPlanner()

    def run(self, state: AgentState) -> AgentState:
        for index in range(state.max_steps):
            step_index = index + 1
            decision = self.planner.plan(state)
            state.planner_decision_count += 1

            if decision["type"] == "final":
                # 计划结束，记录最终步骤和事件，准备生成回答。
                step = AgentStep(
                    step=step_index,
                    type="final",
                    reason=decision.get("reason"),
                )
                state.steps.append(step)
                state.finish_reason = "planner_final"
                state.working_memory.task_status = "ready_to_answer"
                create_agent_step(
                    run_id=state.run_id,
                    step_index=step_index,
                    step_type="final",
                    reason=step.reason,
                    success=True,
                )

                create_agent_event(
                    run_id=state.run_id,
                    event_type=EVENT_AGENT_STEP_FINAL,
                    payload={
                        "step_index": step_index,
                        "reason": step.reason,
                    },
                )

                return state

            tool_name = str(decision["tool_name"])
            arguments = dict(decision.get("arguments", {}))
            tool_span = self._create_tool_span(
                state=state,
                tool_name=tool_name,
                arguments=arguments,
                reason=decision.get("reason"),
            )

            # 检测到重复工具调用，阻断并记录错误，避免 Agent 陷入循环。
            if _has_duplicate_tool_call(state, tool_name, arguments):
                result = {
                    "success": False,
                    "data": None,
                    "error": {
                        "code": "DUPLICATE_TOOL_CALL_BLOCKED",
                        "message": "检测到重复工具调用，已阻断，避免 Agent 陷入循环",
                    },
                    "metadata": {
                        "tool_name": tool_name,
                        "arguments": arguments,
                    },
                }
                # 记录重复工具调用错误步骤，虽然这个步骤没有真正执行工具，但记录下来可以让 Trace 更完整，方便后续分析和优化。
                step = AgentStep(
                    step=step_index,
                    type="error",
                    tool_name=tool_name,
                    arguments=arguments,
                    result=result,
                    success=False,
                    reason=decision.get("reason"),
                    error_code="DUPLICATE_TOOL_CALL_BLOCKED",
                    error_message="重复工具调用已阻断",
                )
                state.steps.append(step)
                state.finish_reason = "duplicate_tool_call_blocked"

                # 记录重复工具调用错误步骤和事件
                create_agent_step(
                    run_id=state.run_id,
                    step_index=step_index,
                    step_type="error",
                    reason=step.reason,
                    tool_name=tool_name,
                    tool_arguments=arguments,
                    tool_result=result,
                    success=False,
                    error_code=step.error_code,
                    error_message=step.error_message,
                )

                create_agent_event(
                    run_id=state.run_id,
                    event_type=EVENT_DUPLICATE_TOOL_CALL_BLOCKED,
                    payload={
                        "step_index": step_index,
                        "tool_name": tool_name,
                        "arguments": arguments,
                    },
                )
                self._finish_tool_span(tool_span, step)

                return state

            create_agent_event(
                run_id=state.run_id,
                event_type=EVENT_AGENT_STEP_START,
                payload={
                    "step_index": step_index,
                    "step_type": "tool_call",
                    "tool_name": tool_name,
                    "arguments": arguments,
                    "reason": decision.get("reason"),
                },
            )

            # 第一次工具调用时，将任务状态更新为 running，反映 Agent 已经开始执行任务。
            state.working_memory.task_status = "running"

            # 解析工具调用步骤，执行工具，并记录步骤结果和事件
            step = self._execute_tool_step(
                state=state,
                step_index=step_index,
                tool_name=tool_name,
                arguments=arguments,
                reason=decision.get("reason"),
                tool_span_id=getattr(tool_span, "id", None),
            )

            # 将步骤结果转换为observation，添加到状态中，为下一轮 planner 提供输入。
            observation = _build_observation(step)
            state.steps.append(step)
            state.observations.append(observation)

            self._finish_tool_span(tool_span, step)

            # 将工具调用结果保存在 WorkMemory 中，供后续决策和回应的上下文补充。
            state.working_memory.add_tool_observation(
                observation.model_dump(mode="json")
            )

            if step.success:
                # 成功的工具调用会被添加到已确认事实中，供后续决策和回应使用。
                state.working_memory.add_fact(f"工具 {step.tool_name} 已成功执行。")
            else:
                # 失败的工具调用会被添加到待解决问题中，提醒后续需要处理这个问题。
                state.working_memory.add_open_question(
                    f"工具 {step.tool_name} 执行失败：{step.error_code or 'UNKNOWN_ERROR'}"
                )

            # 工具调用后不 return，继续下一轮 planner 决策。
            continue

        # 超过最大步骤限制，强制结束 Agent 运行。
        state.finish_reason = "max_steps_reached"
        state.working_memory.task_status = "failed"
        state.working_memory.add_open_question(
            "Agent 达到最大步骤限制，最终回答可能不完整。"
        )

        create_agent_event(
            run_id=state.run_id,
            event_type=EVENT_AGENT_MAX_STEPS_REACHED,
            payload={"max_steps": state.max_steps},
        )
        return state

    def _create_tool_span(
        self,
        *,
        state: AgentState,
        tool_name: str,
        arguments: dict[str, Any],
        reason: str | None,
    ):
        if not state.trace_id or not state.assistant_run_id:
            return None

        source = "internal"
        risk_level = "low"
        try:
            tool = self.tool_registry.get(tool_name)
            source = getattr(tool, "source", source)
            risk_level = getattr(tool, "risk_level", risk_level)
        except Exception:
            pass

        return self.trace_store.create_span(
            TraceSpanCreate(
                trace_id=state.trace_id,
                run_id=state.assistant_run_id,
                parent_span_id=state.agent_span_id or state.parent_span_id,
                conversation_id=state.conversation_id,
                assistant_run_id=state.assistant_run_id,
                agent_run_id=state.run_id,
                span_type=SPAN_TYPE_TOOL_CALL,
                name=tool_name,
                input=redact_dict(
                    {
                        "tool_name": tool_name,
                        "arguments": arguments,
                        "reason": reason,
                    },
                    max_text_chars=1200,
                ),
                metadata={
                    "source": source,
                    "risk_level": risk_level,
                    "step": len(state.steps) + 1,
                },
            )
        )

    def _finish_tool_span(self, span: Any, step: AgentStep) -> None:
        if span is None:
            return

        result = step.result or {}
        self.trace_store.finish_span(
            span.id,
            status="success" if step.success else "error",
            output=redact_dict(
                {
                    "success": step.success,
                    "result": result,
                    "error_code": step.error_code,
                    "error_message": step.error_message,
                },
                max_text_chars=2000,
            ),
            error_code=None if step.success else step.error_code,
            error_message=None if step.success else step.error_message,
            metadata={
                "latency_ms": step.latency_ms,
            },
        )

    def _execute_tool_step(
        self,
        *,
        state: AgentState,
        step_index: int,
        tool_name: str,
        arguments: dict[str, Any],
        reason: str | None,
        tool_span_id: str | None = None,
    ) -> AgentStep:
        """解析工具调用步骤，执行工具，并记录步骤结果和事件

        Args:
            state (AgentState): 当前的 Agent 状态
            step_index (int): 当前步骤的索引
            tool_name (str): 工具名称
            arguments (dict[str, Any]): 工具调用参数
            reason (str | None): 工具调用的原因

        Returns:
            AgentStep: 工具调用步骤的结果
        """
        start = perf_counter()

        try:
            tool = self.tool_registry.get(tool_name)
            execution_arguments = self._build_execution_arguments(
                state=state,
                tool=tool,
                arguments=arguments,
                tool_span_id=tool_span_id,
            )
            # 验证工具参数是否合法，合法则执行工具，否则记录参数错误
            self.tool_registry.validate_arguments(tool_name, execution_arguments)
            result = tool.run(execution_arguments)
            result = limit_tool_result(
                result
            )  # 对工具结果进行长度限制，避免过大结果导致后续处理问题

            latency_ms = int((perf_counter() - start) * 1000)
            max_latency_ms = get_agent_tool_timeout_seconds() * 1000
            success = bool(result.get("success"))

            if latency_ms > max_latency_ms:
                success = False
                result = {
                    "success": False,
                    "data": None,
                    "error": {
                        "code": "TOOL_TIMEOUT_ERROR",
                        "message": f"Tool execution exceeded {max_latency_ms} ms",
                    },
                    "metadata": {
                        "tool_name": tool_name,
                        "latency_ms": latency_ms,
                    },
                }

            step = AgentStep(
                step=step_index,
                type="tool_call",
                tool_name=tool_name,
                arguments=arguments,
                result=result,
                success=success,
                latency_ms=latency_ms,
                reason=reason,
                error_code=(result.get("error") or {}).get("code"),
                error_message=(result.get("error") or {}).get("message"),
            )

            create_agent_step(
                run_id=state.run_id,
                step_index=step_index,
                step_type="tool_call",
                reason=reason,
                tool_name=tool_name,
                tool_arguments=arguments,
                tool_result=result,
                success=success,
                latency_ms=latency_ms,
                error_code=step.error_code,
                error_message=step.error_message,
            )

            create_agent_event(
                run_id=state.run_id,
                event_type=EVENT_TOOL_RESULT,
                payload={
                    "step_index": step_index,
                    "tool_name": tool_name,
                    "success": success,
                    "latency_ms": latency_ms,
                },
            )

            return step

        except ValidationError as exc:
            # 工具参数验证错误，记录错误步骤和事件
            return self._record_tool_error_step(
                state=state,
                step_index=step_index,
                tool_name=tool_name,
                arguments=arguments,
                reason=reason,
                start=start,
                code="TOOL_ARGUMENT_SCHEMA_ERROR",
                message=exc.message,
            )

        except Exception as exc:
            return self._record_tool_error_step(
                state=state,
                step_index=step_index,
                tool_name=tool_name,
                arguments=arguments,
                reason=reason,
                start=start,
                code="TOOL_EXECUTION_ERROR",
                message=str(exc),
            )

    def _build_execution_arguments(
        self,
        *,
        state: AgentState,
        tool: Any,
        arguments: dict[str, Any],
        tool_span_id: str | None,
    ) -> dict[str, Any]:
        if getattr(tool, "source", "internal") != "mcp":
            return arguments

        if not state.trace_id or not state.assistant_run_id:
            return arguments

        return {
            **arguments,
            "_trace": {
                "trace_id": state.trace_id,
                "parent_span_id": tool_span_id
                or state.agent_span_id
                or state.parent_span_id,
                "run_id": state.assistant_run_id,
                "conversation_id": state.conversation_id,
                "assistant_run_id": state.assistant_run_id,
                "agent_run_id": state.run_id,
            },
        }

    def _record_tool_error_step(
        self,
        *,
        state: AgentState,
        step_index: int,
        tool_name: str,
        arguments: dict[str, Any],
        reason: str | None,
        start: float,
        code: str,
        message: str,
    ) -> AgentStep:
        latency_ms = int((perf_counter() - start) * 1000)
        result = {
            "success": False,
            "data": None,
            "error": {
                "code": code,
                "message": message,
            },
            "metadata": {
                "tool_name": tool_name,
                "latency_ms": latency_ms,
            },
        }

        step = AgentStep(
            step=step_index,
            type="tool_call",
            tool_name=tool_name,
            arguments=arguments,
            result=result,
            success=False,
            latency_ms=latency_ms,
            reason=reason,
            error_code=code,
            error_message=message,
        )

        create_agent_step(
            run_id=state.run_id,
            step_index=step_index,
            step_type="tool_call",
            reason=reason,
            tool_name=tool_name,
            tool_arguments=arguments,
            tool_result=result,
            success=False,
            latency_ms=latency_ms,
            error_code=code,
            error_message=message,
        )

        create_agent_event(
            run_id=state.run_id,
            event_type=EVENT_TOOL_ERROR,
            payload={
                "step_index": step_index,
                "tool_name": tool_name,
                "latency_ms": latency_ms,
                "error": result["error"],
            },
        )

        return step
