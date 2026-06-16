from __future__ import annotations

from typing import Any
import requests

from .schemas import AssistantEvalOutput, EvalCase, EvalRunConfig
from .sse import parse_sse_lines


class AssistantEvalClient:
    """通过真实 Assistant API 执行评测。

    这里刻意不直接 import AssistantOrchestrator。
    原因：
    1. Eval 应尽量模拟真实前端调用。
    2. 可以覆盖 FastAPI router、SSE、序列化问题。
    3. 后续也方便在 CI 或远程环境执行。
    """

    def __init__(self, config: EvalRunConfig) -> None:
        self.config = config
        self.session = requests.Session()

    def run_case(self, case: EvalCase) -> AssistantEvalOutput:
        url = (
            f"{self.config.base_url}"
            f"/conversations/{self.config.conversation_id}/assistant/stream"
        )

        payload: dict[str, Any] = {
            "message": case.message,
            "mode": case.mode,
            "options": case.options,
        }

        if self.config.model:
            payload["model"] = self.config.model
        if self.config.provider:
            payload["provider"] = self.config.provider

        response = self.session.post(
            url,
            json=payload,
            timeout=self.config.timeout_seconds,
            stream=True,
        )
        response.raise_for_status()

        events = parse_sse_lines(response.iter_lines(decode_unicode=True))
        output = self._collect_output(events)

        if output.assistant_run_id:
            run_detail = self.get_assistant_run(output.assistant_run_id)
            trace = run_detail.get("trace") if isinstance(run_detail, dict) else None
            output.multi_agent = (payload.get("trace") or {}).get("multi_agent") or None
            if trace and output.trace is None:
                output.trace = trace

        return output

    def get_assistant_run(self, run_id: str) -> dict[str, Any]:
        url = f"{self.config.base_url}/assistant/runs/{run_id}"
        response = self.session.get(url, timeout=self.config.timeout_seconds)
        response.raise_for_status()
        return response.json()

    def _collect_output(self, events: list[dict[str, Any]]) -> AssistantEvalOutput:
        answer_parts: list[str] = []
        output = AssistantEvalOutput(events=events)

        for item in events:
            event = item.get("event")
            data = item.get("data")

            if event == "assistant_start" and isinstance(data, dict):
                output.assistant_run_id = data.get("assistant_run_id")
                continue

            if event == "route_decision" and isinstance(data, dict):
                output.route_decision = data
                continue

            if event == "long_term_memory_item" and isinstance(data, dict):
                output.memories.append(data)
                continue

            if event == "context_assembled" and isinstance(data, dict):
                output.context = data
                continue

            if event == "tool_call_end" and isinstance(data, dict):
                output.tool_calls.append(data)
                continue

            if event == "delta" and isinstance(data, dict):
                answer_parts.append(str(data.get("delta") or ""))
                continue

            if event == "assistant_end" and isinstance(data, dict):
                output.assistant_run_id = (
                    data.get("assistant_run_id") or output.assistant_run_id
                )
                output.assistant_message_id = data.get("assistant_message_id")
                output.agent_run_id = data.get("agent_run_id")
                output.latency_ms = data.get("latency_ms")
                output.sources = data.get("sources") or []
                output.trace = data.get("trace")
                output.trace_summary = data.get("trace_summary")

                # assistant_end 中的 tool_calls 更完整，优先使用。
                if data.get("tool_calls"):
                    output.tool_calls = data.get("tool_calls") or []
                continue

            if event == "error" and isinstance(data, dict):
                output.error = data
                continue

        output.answer = "".join(answer_parts).strip()
        return output
