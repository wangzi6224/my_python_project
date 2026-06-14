from __future__ import annotations

from typing import Any

import pytest
from jsonschema import validate

from src.app.services.agent.loop import AgentLoop
from src.app.services.agent.state import AgentState
from src.app.services.observability.trace_schema import SPAN_TYPE_TOOL_CALL


class FakeSpan:
    id = "span-1"


class FakeTraceStore:
    created: list[dict[str, Any]] = []
    finished: list[dict[str, Any]] = []

    def create_span(self, payload: Any) -> FakeSpan:
        self.created.append(payload.model_dump(mode="json"))
        return FakeSpan()

    def finish_span(self, span_id: str, **kwargs: Any) -> FakeSpan:
        self.finished.append({"span_id": span_id, **kwargs})
        return FakeSpan()


class FakeTool:
    name = ""
    description = ""
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": False,
    }

    def run(self, arguments: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError


class FakeSearchDocsTool(FakeTool):
    name = "search_docs"
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "top_k": {"type": "integer"},
            "score_threshold": {"type": "number"},
        },
        "required": ["query"],
        "additionalProperties": False,
    }

    def run(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return {
            "success": True,
            "tool_name": self.name,
            "data": {
                "chunks": [
                    {
                        "chunk_id": "chunk-1",
                        "document_id": "doc-1",
                        "filename": "button.md",
                        "content": "Button 组件规范片段",
                        "score": 0.9,
                    }
                ]
            },
            "metadata": arguments,
        }


class FakeReadDocTool(FakeTool):
    name = "read_doc"
    parameters = {
        "type": "object",
        "properties": {
            "document_id": {"type": "string"},
            "max_chars": {"type": "integer"},
        },
        "required": ["document_id"],
        "additionalProperties": False,
    }

    def run(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return {
            "success": True,
            "tool_name": self.name,
            "data": {
                "document_id": arguments["document_id"],
                "filename": "button.md",
                "content": "完整 Button 组件规范内容",
                "truncated": False,
            },
            "metadata": arguments,
        }


class FakeRegistry:
    def __init__(self) -> None:
        self.tools = {
            "search_docs": FakeSearchDocsTool(),
            "read_doc": FakeReadDocTool(),
        }

    def get(self, name: str) -> FakeTool:
        return self.tools[name]

    def validate_arguments(self, tool_name: str, arguments: dict[str, Any]) -> None:
        validate(instance=arguments, schema=self.tools[tool_name].parameters)


@pytest.fixture(autouse=True)
def patch_trace_store(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "src.app.services.agent.loop.create_agent_step",
        lambda **kwargs: {"id": "step-id", **kwargs},
    )
    monkeypatch.setattr(
        "src.app.services.agent.loop.create_agent_event",
        lambda **kwargs: {"id": "event-id", **kwargs},
    )
    FakeTraceStore.created = []
    FakeTraceStore.finished = []
    monkeypatch.setattr(
        "src.app.services.agent.loop.TraceStore",
        FakeTraceStore,
    )


def build_state(question: str, max_steps: int = 3) -> AgentState:
    return AgentState(
        run_id="run-1",
        conversation_id="conversation-1",
        user_message_id="message-1",
        question=question,
        messages=[],
        max_steps=max_steps,
        model="test-model",
        top_k=5,
        score_threshold=0.3,
    )


def test_agent_loop_can_search_then_read_then_final() -> None:
    loop = AgentLoop(tool_registry=FakeRegistry(), planner_type="rule")  # type: ignore[arg-type]
    state = build_state("根据知识库详细分析 Button 组件规范", max_steps=3)

    result = loop.run(state)

    tool_steps = [step for step in result.steps if step.type == "tool_call"]

    assert [step.tool_name for step in tool_steps] == ["search_docs", "read_doc"]
    assert result.steps[-1].type == "final"
    assert result.finish_reason == "planner_final"
    assert result.planner_decision_count == 3
    assert result.planner_fallback_count == 0
    assert len(result.observations) == 2
    assert result.observations[0].tool_name == "search_docs"
    assert result.observations[1].tool_name == "read_doc"


def test_agent_loop_respects_max_steps() -> None:
    loop = AgentLoop(tool_registry=FakeRegistry(), planner_type="rule")  # type: ignore[arg-type]
    state = build_state("根据知识库详细分析 Button 组件规范", max_steps=1)

    result = loop.run(state)

    assert len(result.steps) == 1
    assert result.steps[0].tool_name == "search_docs"
    assert result.finish_reason == "max_steps_reached"
    assert result.planner_decision_count == 1


def test_agent_loop_records_validation_error_as_observation() -> None:
    class BadPlanner:
        def plan(self, state: AgentState) -> dict[str, Any]:
            return {
                "type": "tool_call",
                "tool_name": "search_docs",
                "arguments": {},
                "reason": "故意缺少 query",
            }

    loop = AgentLoop(tool_registry=FakeRegistry(), planner_type="rule")  # type: ignore[arg-type]
    loop.planner = BadPlanner()  # type: ignore[assignment]
    state = build_state("根据知识库查询 Button", max_steps=1)

    result = loop.run(state)

    assert len(result.steps) == 1
    assert result.steps[0].success is False
    assert result.steps[0].error_code == "TOOL_ARGUMENT_SCHEMA_ERROR"
    assert len(result.observations) == 1
    assert result.observations[0].success is False


def test_agent_loop_blocks_duplicate_tool_call() -> None:
    class DuplicatePlanner:
        def plan(self, state: AgentState) -> dict[str, Any]:
            return {
                "type": "tool_call",
                "tool_name": "search_docs",
                "arguments": {
                    "query": "Button",
                    "top_k": 5,
                    "score_threshold": 0.3,
                },
                "reason": "重复调用测试",
            }

    loop = AgentLoop(tool_registry=FakeRegistry(), planner_type="rule")  # type: ignore[arg-type]
    loop.planner = DuplicatePlanner()  # type: ignore[assignment]
    state = build_state("根据知识库查询 Button", max_steps=3)

    result = loop.run(state)

    assert result.steps[0].type == "tool_call"
    assert result.steps[1].type == "error"
    assert result.steps[1].error_code == "DUPLICATE_TOOL_CALL_BLOCKED"
    assert result.finish_reason == "duplicate_tool_call_blocked"
    assert result.planner_decision_count == 2


def test_agent_loop_records_tool_call_span() -> None:
    loop = AgentLoop(tool_registry=FakeRegistry(), planner_type="rule")  # type: ignore[arg-type]
    state = build_state("根据知识库查询 Button", max_steps=1).model_copy(
        update={
            "trace_id": "trace-1",
            "assistant_run_id": "assistant-run-1",
            "agent_span_id": "agent-span-1",
        }
    )

    loop.run(state)

    assert FakeTraceStore.created[0]["span_type"] == SPAN_TYPE_TOOL_CALL
    assert FakeTraceStore.created[0]["parent_span_id"] == "agent-span-1"
    assert FakeTraceStore.finished[0]["status"] == "success"


def test_agent_loop_records_tool_error_span() -> None:
    class BadPlanner:
        def plan(self, state: AgentState) -> dict[str, Any]:
            return {
                "type": "tool_call",
                "tool_name": "search_docs",
                "arguments": {"api_key": "secret-value"},
                "reason": "故意缺少 query",
            }

    loop = AgentLoop(tool_registry=FakeRegistry(), planner_type="rule")  # type: ignore[arg-type]
    loop.planner = BadPlanner()  # type: ignore[assignment]
    state = build_state("根据知识库查询 Button", max_steps=1).model_copy(
        update={
            "trace_id": "trace-1",
            "assistant_run_id": "assistant-run-1",
            "agent_span_id": "agent-span-1",
        }
    )

    loop.run(state)

    assert FakeTraceStore.created[0]["input"]["arguments"]["api_key"] == "[REDACTED]"
    assert FakeTraceStore.finished[0]["status"] == "error"
    assert FakeTraceStore.finished[0]["error_code"] == "TOOL_ARGUMENT_SCHEMA_ERROR"
