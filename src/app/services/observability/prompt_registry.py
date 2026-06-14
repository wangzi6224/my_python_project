from __future__ import annotations

from dataclasses import dataclass

from src.app.services.observability.trace_schema import SPAN_TYPE_CONTEXT_COMPRESS


@dataclass(frozen=True)
class PromptSpec:
    name: str
    version: str
    description: str


PROMPT_REGISTRY: dict[str, PromptSpec] = {
    "assistant.chat": PromptSpec(
        name="assistant.chat",
        version="2026-06-10.chat.v1",
        description="普通 Chat path 的系统提示词和上下文组装规则",
    ),
    "agent.planner": PromptSpec(
        name="agent.planner",
        version="2026-06-10.planner.v1",
        description="Agent LLM Planner 决策提示词",
    ),
    "agent.final_answer": PromptSpec(
        name="agent.final_answer",
        version="2026-06-10.agent-final.v1",
        description="Agent 工具观察结果汇总生成最终回答",
    ),
    "memory.write": PromptSpec(
        name="memory.write",
        version="2026-06-10.memory-write.v1",
        description="长期记忆抽取提示词",
    ),
    SPAN_TYPE_CONTEXT_COMPRESS.value: PromptSpec(
        name=SPAN_TYPE_CONTEXT_COMPRESS.value,
        version="2026-06-10.context-compress.v1",
        description="超长上下文压缩提示词",
    ),
}


def get_prompt_version(name: str) -> str:
    spec = PROMPT_REGISTRY.get(name)
    if spec is None:
        return "unknown"
    return spec.version
