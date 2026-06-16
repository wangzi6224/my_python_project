from __future__ import annotations

from json import dumps
from typing import Any, Final, Literal

EVENT_ASSISTANT_START: Final = "assistant_start"  # Assistant 流式响应开始。
EVENT_ASSISTANT_END: Final = "assistant_end"  # Assistant 流式响应完成。
EVENT_ROUTE_DECISION: Final = "route_decision"  # Assistant 自动路由决策结果。
EVENT_TOOL_CALL_START: Final = "tool_call_start"  # Agent 工具调用开始。
EVENT_TOOL_CALL_END: Final = "tool_call_end"  # Agent 工具调用完成。
EVENT_DELTA: Final = "delta"  # 模型增量文本片段。
EVENT_ERROR: Final = "error"  # 流式接口错误事件。
EVENT_DONE: Final = "done"  # SSE 流结束标记。

EVENT_MESSAGE_START: Final = "message_start"  # 旧会话流消息开始。
EVENT_MESSAGE_END: Final = "message_end"  # 旧会话流消息完成。

EVENT_AGENT_RUN_START: Final = "agent_run_start"  # Agent 运行开始。
EVENT_AGENT_RUN_END: Final = "agent_run_end"  # Agent 运行结束。
EVENT_PLANNER_DECISION: Final = "planner_decision"  # Planner 生成有效决策。
EVENT_PLANNER_FALLBACK: Final = "planner_fallback"  # Planner 异常后使用兜底决策。
EVENT_AGENT_STEP_START: Final = "agent_step_start"  # Agent 单步执行开始。
EVENT_TOOL_RESULT: Final = "tool_result"  # 工具调用返回结果。
EVENT_TOOL_ERROR: Final = "tool_error"  # 工具调用执行失败。
EVENT_DUPLICATE_TOOL_CALL_BLOCKED: Final = (
    "duplicate_tool_call_blocked"  # 重复工具调用被阻断。
)
EVENT_AGENT_STEP_FINAL: Final = "agent_step_final"  # Agent 提前进入最终回答步骤。
EVENT_AGENT_MAX_STEPS_REACHED: Final = (
    "agent_max_steps_reached"  # Agent 达到最大步骤限制。
)

EVENT_SHORT_TERM_MEMORY_LOADED: Final = "short_term_memory_loaded"  # 短期记忆加载完成。
EVENT_LONG_TERM_MEMORY_RETRIEVAL_START: Final = (
    "long_term_memory_retrieval_start"  # 长期记忆检索开始。
)
EVENT_LONG_TERM_MEMORY_ITEM: Final = (
    "long_term_memory_item"  # 长期记忆检索到单条记忆项。
)
EVENT_LONG_TERM_MEMORY_WRITE: Final = "long_term_memory_write"  # 长期记忆写入完成。
EVENT_WORKING_MEMORY_UPDATED: Final = "working_memory_updated"  # 工作记忆更新完成。
EVENT_CONTEXT_ASSEMBLED: Final = (
    "context_assembled"  # 上下文组装完成，包含最终进入模型的上下文摘要信息。
)

EVENT_MULTI_AGENT_RUN_START = "multi_agent_run_start"
EVENT_MULTI_AGENT_ROLE_START = "multi_agent_role_start"
EVENT_MULTI_AGENT_ROLE_END = "multi_agent_role_end"
EVENT_MULTI_AGENT_HANDOFF = "multi_agent_handoff"
EVENT_MULTI_AGENT_REVIEW = "multi_agent_review"

AssistantStreamEvent = Literal[
    "assistant_start",
    "route_decision",
    "short_term_memory_loaded",
    "long_term_memory_retrieval_start",
    "long_term_memory_item",
    "long_term_memory_write",
    "working_memory_updated",
    "context_assembled",
    "tool_call_start",
    "tool_call_end",
    "delta",
    "assistant_end",
    "error",
    "done",
    "multi_agent_run_start",
    "multi_agent_role_start",
    "multi_agent_role_end",
    "multi_agent_handoff",
    "multi_agent_review",
]

ConversationStreamEvent = Literal[
    "message_start",
    "delta",
    "message_end",
    "error",
    "done",
]

AgentTraceEvent = Literal[
    "agent_run_start",
    "agent_run_end",
    "planner_decision",
    "planner_fallback",
    "agent_step_start",
    "tool_result",
    "tool_error",
    "duplicate_tool_call_blocked",
    "agent_step_final",
    "agent_max_steps_reached",
]

ASSISTANT_STREAM_EVENTS: tuple[AssistantStreamEvent, ...] = (
    EVENT_ASSISTANT_START,
    EVENT_ROUTE_DECISION,
    EVENT_SHORT_TERM_MEMORY_LOADED,
    EVENT_LONG_TERM_MEMORY_RETRIEVAL_START,
    EVENT_LONG_TERM_MEMORY_ITEM,
    EVENT_LONG_TERM_MEMORY_WRITE,
    EVENT_WORKING_MEMORY_UPDATED,
    EVENT_CONTEXT_ASSEMBLED,
    EVENT_TOOL_CALL_START,
    EVENT_TOOL_CALL_END,
    EVENT_DELTA,
    EVENT_ASSISTANT_END,
    EVENT_ERROR,
    EVENT_DONE,
    EVENT_MULTI_AGENT_RUN_START,
    EVENT_MULTI_AGENT_ROLE_START,
    EVENT_MULTI_AGENT_ROLE_END,
    EVENT_MULTI_AGENT_HANDOFF,
    EVENT_MULTI_AGENT_REVIEW,
)

CONVERSATION_STREAM_EVENTS: tuple[ConversationStreamEvent, ...] = (
    EVENT_MESSAGE_START,
    EVENT_DELTA,
    EVENT_MESSAGE_END,
    EVENT_ERROR,
    EVENT_DONE,
)

AGENT_TRACE_EVENTS: tuple[AgentTraceEvent, ...] = (
    EVENT_AGENT_RUN_START,
    EVENT_AGENT_RUN_END,
    EVENT_PLANNER_DECISION,
    EVENT_PLANNER_FALLBACK,
    EVENT_AGENT_STEP_START,
    EVENT_TOOL_RESULT,
    EVENT_TOOL_ERROR,
    EVENT_DUPLICATE_TOOL_CALL_BLOCKED,
    EVENT_AGENT_STEP_FINAL,
    EVENT_AGENT_MAX_STEPS_REACHED,
)

# Backward-compatible alias for the existing helper annotation.
event = AssistantStreamEvent


def sse_event(event: AssistantStreamEvent, data: Any) -> str:
    """构造标准 SSE 字符串。"""

    if isinstance(data, str):
        payload = data
    else:
        payload = dumps(data, ensure_ascii=False)

    return f"event: {event}\ndata: {payload}\n\n"
