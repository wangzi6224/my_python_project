from __future__ import annotations

from time import perf_counter
from typing import Any

from src.app.config import get_mcp_max_result_chars
from src.app.services.mcp.audit_store import McpAuditStore
from src.app.services.mcp.client import McpClient
from src.app.services.mcp.permission import McpPermission
from src.app.services.mcp.schemas import McpServerConfig, McpToolSpec
from src.app.services.observability.redaction import redact_dict
from src.app.services.observability.trace_schema import (
    SPAN_TYPE_MCP_CALL,
    TraceSpanCreate,
)
from src.app.services.observability.trace_store import TraceStore
from src.app.services.tools.base import Tool
from src.app.services.tools.result import tool_error, tool_success


class McpToolAdapter(Tool):
    """把外部 MCP Tool 适配成 NexusAI 内部 Tool。"""

    def __init__(
        self,
        *,
        server: McpServerConfig,
        spec: McpToolSpec,
        client: McpClient | None = None,
        permission: McpPermission | None = None,
        audit_store: McpAuditStore | None = None,
        trace_store: TraceStore | None = None,
    ) -> None:
        self.server = server
        self.spec = spec
        self.client = client or McpClient()
        self.permission = permission or McpPermission()
        self.audit_store = audit_store or McpAuditStore()
        self.trace_store = trace_store or TraceStore()

        self.name = spec.full_name
        self.description = f"[MCP:{spec.server_name}] {spec.description}"
        self.parameters = spec.input_schema or {"type": "object", "properties": {}}
        self.source = "mcp"
        self.risk_level = spec.risk_level

    def run(self, arguments: dict[str, Any]) -> dict[str, Any]:
        trace_context = self._extract_trace_context(arguments)
        public_arguments = self._strip_trace(arguments)

        try:
            self.permission.validate_tool(self.spec)
        except PermissionError as exc:
            return tool_error(
                tool_name=self.name,
                code="MCP_PERMISSION_DENIED",
                message=str(exc),
                metadata={
                    "source": "mcp",
                    "server_name": self.spec.server_name,
                    "tool_name": self.spec.tool_name,
                    "risk_level": self.spec.risk_level,
                },
            )

        span = self._create_mcp_span(
            trace_context=trace_context,
            arguments=public_arguments,
        )

        call_start = perf_counter()
        try:
            result = self.client.call_tool(
                server=self.server,
                tool_name=self.spec.tool_name,
                full_name=self.spec.full_name,
                arguments=public_arguments,
            )
        except Exception as exc:
            latency_ms = int((perf_counter() - call_start) * 1000)
            if span is not None:
                self.trace_store.finish_span(
                    span.id,
                    status="error",
                    output={
                        "server_name": self.spec.server_name,
                        "tool_name": self.spec.tool_name,
                        "latency_ms": latency_ms,
                        "result_chars": 0,
                    },
                    error_code=exc.__class__.__name__,
                    error_message=str(exc),
                )
            raise

        max_chars = get_mcp_max_result_chars()
        content = result.content[:max_chars]
        truncated = len(result.content) > max_chars

        if span is not None:
            self.trace_store.finish_span(
                span.id,
                status="success" if result.success else "error",
                output={
                    "server_name": result.server_name,
                    "tool_name": result.tool_name,
                    "latency_ms": result.latency_ms,
                    "result_chars": len(result.content or ""),
                    "success": result.success,
                },
                error_code=None if result.success else result.error_code,
                error_message=None if result.success else result.error_message,
                metadata={
                    "server_name": result.server_name,
                    "tool_name": result.tool_name,
                    "full_tool_name": result.full_name,
                    "latency_ms": result.latency_ms,
                    "result_chars": len(result.content or ""),
                },
            )

        self.audit_store.create_log(
            result=result,
            arguments=public_arguments,
            conversation_id=trace_context.get("conversation_id"),
            assistant_run_id=trace_context.get("assistant_run_id"),
            agent_run_id=trace_context.get("agent_run_id"),
            risk_level=self.spec.risk_level,
            metadata={"truncated": truncated},
        )

        if not result.success:
            return tool_error(
                tool_name=self.name,
                code=result.error_code or "MCP_TOOL_CALL_FAILED",
                message=result.error_message or "MCP 工具调用失败",
                latency_ms=result.latency_ms,
                metadata={
                    "source": "mcp",
                    "server_name": self.spec.server_name,
                    "tool_name": self.spec.tool_name,
                    "risk_level": self.spec.risk_level,
                },
            )

        return tool_success(
            tool_name=self.name,
            data={
                "content": content,
                "truncated": truncated,
                "server_name": self.spec.server_name,
                "tool_name": self.spec.tool_name,
            },
            latency_ms=result.latency_ms,
            metadata={
                "source": "mcp",
                "server_name": self.spec.server_name,
                "tool_name": self.spec.tool_name,
                "full_tool_name": self.spec.full_name,
                "risk_level": self.spec.risk_level,
                "truncated": truncated,
            },
        )

    def _extract_trace_context(self, arguments: dict[str, Any]) -> dict[str, str]:
        trace = arguments.get("_trace")

        if not isinstance(trace, dict):
            return {}

        return {
            key: value
            for key, value in trace.items()
            if key
            in {
                "trace_id",
                "parent_span_id",
                "run_id",
                "conversation_id",
                "assistant_run_id",
                "agent_run_id",
            }
            and isinstance(value, str)
            and value
        }

    def _strip_trace(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in arguments.items() if key != "_trace"}

    def _create_mcp_span(
        self,
        *,
        trace_context: dict[str, str],
        arguments: dict[str, Any],
    ):
        trace_id = trace_context.get("trace_id")
        run_id = trace_context.get("run_id") or trace_context.get("assistant_run_id")

        if not trace_id or not run_id:
            return None

        return self.trace_store.create_span(
            TraceSpanCreate(
                trace_id=trace_id,
                run_id=run_id,
                parent_span_id=trace_context.get("parent_span_id"),
                conversation_id=trace_context.get("conversation_id"),
                assistant_run_id=trace_context.get("assistant_run_id"),
                agent_run_id=trace_context.get("agent_run_id"),
                span_type=SPAN_TYPE_MCP_CALL,
                name=self.spec.full_name,
                input=redact_dict(
                    {
                        "server_name": self.spec.server_name,
                        "tool_name": self.spec.tool_name,
                        "full_tool_name": self.spec.full_name,
                        "arguments": arguments,
                    },
                    max_text_chars=1200,
                ),
                metadata={
                    "source": "mcp",
                    "server_name": self.spec.server_name,
                    "tool_name": self.spec.tool_name,
                    "full_tool_name": self.spec.full_name,
                    "risk_level": self.spec.risk_level,
                },
            )
        )
