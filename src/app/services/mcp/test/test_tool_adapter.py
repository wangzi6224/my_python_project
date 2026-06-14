from __future__ import annotations

from typing import Any

from src.app.services.mcp.schemas import McpServerConfig, McpToolCallResult, McpToolSpec
from src.app.services.mcp.tool_adapter import McpToolAdapter
from src.app.services.observability.trace_schema import SPAN_TYPE_MCP_CALL
from src.app.services.tools.registry import ToolRegistry


class FakeSpan:
    id = "mcp-span-1"


class FakeTraceStore:
    def __init__(self) -> None:
        self.created: list[dict[str, Any]] = []
        self.finished: list[dict[str, Any]] = []

    def create_span(self, payload: Any) -> FakeSpan:
        self.created.append(payload.model_dump(mode="json"))
        return FakeSpan()

    def finish_span(self, span_id: str, **kwargs: Any) -> FakeSpan:
        self.finished.append({"span_id": span_id, **kwargs})
        return FakeSpan()


class FakeClient:
    def __init__(self, result: McpToolCallResult) -> None:
        self.result = result
        self.arguments: dict[str, Any] | None = None

    def call_tool(self, **kwargs: Any) -> McpToolCallResult:
        self.arguments = kwargs["arguments"]
        return self.result


class FakeAuditStore:
    def __init__(self) -> None:
        self.logs: list[dict[str, Any]] = []

    def create_log(self, **kwargs: Any) -> dict[str, Any]:
        self.logs.append(kwargs)
        return {"id": "audit-1", **kwargs}


class FakePermission:
    def validate_tool(self, tool: McpToolSpec) -> None:
        return None


def build_adapter(
    *,
    result: McpToolCallResult,
    trace_store: FakeTraceStore | None = None,
    audit_store: FakeAuditStore | None = None,
) -> tuple[McpToolAdapter, FakeClient, FakeTraceStore, FakeAuditStore]:
    server = McpServerConfig(
        name="github",
        command="mcp-github",
        env={"API_KEY": "must-not-enter-trace"},
    )
    spec = McpToolSpec(
        server_name="github",
        tool_name="search",
        full_name="mcp__github__search",
        description="Search issues",
        input_schema={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
            "additionalProperties": False,
        },
        risk_level="medium",
    )
    client = FakeClient(result)
    trace_store = trace_store or FakeTraceStore()
    audit_store = audit_store or FakeAuditStore()
    adapter = McpToolAdapter(
        server=server,
        spec=spec,
        client=client,  # type: ignore[arg-type]
        permission=FakePermission(),  # type: ignore[arg-type]
        audit_store=audit_store,  # type: ignore[arg-type]
        trace_store=trace_store,  # type: ignore[arg-type]
    )
    return adapter, client, trace_store, audit_store


def build_trace() -> dict[str, str]:
    return {
        "trace_id": "trace-1",
        "parent_span_id": "tool-span-1",
        "run_id": "assistant-run-1",
        "conversation_id": "conversation-1",
        "assistant_run_id": "assistant-run-1",
        "agent_run_id": "agent-run-1",
    }


def test_mcp_adapter_creates_success_span_without_raw_result() -> None:
    adapter, client, trace_store, audit_store = build_adapter(
        result=McpToolCallResult(
            server_name="github",
            tool_name="search",
            full_name="mcp__github__search",
            success=True,
            content="search result",
            raw_result={"secret": "raw"},
            latency_ms=12,
        )
    )

    result = adapter.run({"query": "bug", "_trace": build_trace()})

    assert result["success"] is True
    assert client.arguments == {"query": "bug"}
    assert audit_store.logs[0]["arguments"] == {"query": "bug"}
    assert audit_store.logs[0]["assistant_run_id"] == "assistant-run-1"
    assert trace_store.created[0]["span_type"] == SPAN_TYPE_MCP_CALL
    assert trace_store.created[0]["parent_span_id"] == "tool-span-1"
    assert trace_store.created[0]["input"]["arguments"] == {"query": "bug"}
    assert "env" not in trace_store.created[0]["input"]
    assert trace_store.finished[0]["status"] == "success"
    assert trace_store.finished[0]["output"]["result_chars"] == len("search result")
    assert "raw_result" not in trace_store.finished[0]["output"]


def test_mcp_adapter_creates_error_span() -> None:
    adapter, _, trace_store, _ = build_adapter(
        result=McpToolCallResult(
            server_name="github",
            tool_name="search",
            full_name="mcp__github__search",
            success=False,
            error_code="MCP_TOOL_CALL_FAILED",
            error_message="server failed",
            latency_ms=9,
        )
    )

    result = adapter.run({"query": "bug", "_trace": build_trace()})

    assert result["success"] is False
    assert trace_store.finished[0]["status"] == "error"
    assert trace_store.finished[0]["error_code"] == "MCP_TOOL_CALL_FAILED"
    assert trace_store.finished[0]["error_message"] == "server failed"


def test_tool_registry_validation_ignores_internal_trace() -> None:
    adapter, _, _, _ = build_adapter(
        result=McpToolCallResult(
            server_name="github",
            tool_name="search",
            full_name="mcp__github__search",
            success=True,
        )
    )
    registry = ToolRegistry(allowed_tools=[adapter.name])
    registry.register(adapter)

    registry.validate_arguments(
        adapter.name,
        {"query": "bug", "_trace": build_trace()},
    )
