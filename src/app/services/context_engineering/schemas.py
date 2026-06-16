# src/app/services/context_engineering/schemas.py
from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field

from src.app.config import get_context_context_token_by_config

ContextItemType = Literal[
    "system_instruction",  # 系统指令，通常由开发者预设，或由系统自动生成（如安全策略）。优先级最高，通常不允许压缩。
    "safety_policy",  # 安全策略，通常由系统自动生成，或由开发者预设。优先级很高，通常不允许压缩。
    "conversation_summary",  # 对话总结，通常由系统自动生成，或由开发者预设。优先级较高，允许压缩。
    "conversation_state",  # 对话状态，通常由系统自动生成，或由开发者预设。优先级较高，允许压缩。
    "recent_message",  # 最近消息，通常来自用户和助手的历史消息。优先级较高，允许压缩。
    "long_term_memory",  # 长期记忆，通常来自知识库或记忆系统。优先级中等，允许压缩。
    "working_memory",  # 工作记忆，通常来自当前对话过程中的临时信息。优先级中等，允许压缩。
    "retrieved_source",  # 检索到的资料，通常来自外部检索工具。优先级中等，允许压缩。
    "read_document",  # 阅读到的文档内容，通常来自文档阅读工具。优先级中等，允许压缩。
    "tool_observation",  # 工具调用结果，通常来自外部工具调用。优先级较低，允许压缩。
    "output_requirement",  # 输出要求，通常由系统自动生成，或由开发者预设。优先级较低，允许压缩。
    "multi_agent_artifact",
    "multi_agent_handoff",
]

ContextPlacement = Literal[
    "system",  # 高权限系统区，只允许系统自有策略
    "user_data",  # 用户消息中的资料区
    "history",  # 历史消息区
]

ContextSource = Literal[
    "system",
    "conversation",
    "short_term_memory",
    "long_term_memory",
    "working_memory",
    "agent_tool",
    "assistant_runtime",
    "multi_agent",
]


class ContextItem(BaseModel):
    """候选上下文项。

    设计目的：
    1. 统一 memory / summary / recent messages / tool observations 等来源。
    2. 给 ranking / budget / compression / audit 提供稳定字段。
    3. 最终 trace 可以解释每个上下文为什么被选中或丢弃。
    """

    id: str
    type: ContextItemType
    source: ContextSource
    placement: ContextPlacement

    content: str = Field(min_length=1)

    # priority 是硬优先级，越大越重要。
    # 例如 system_instruction=100，current user question=95，tool result=80。
    priority: int = Field(default=50, ge=0, le=100)

    # score 是软排序分数，通常来自 memory score、retrieval score、rerank score。
    score: float = Field(default=0.5, ge=0, le=1)

    estimated_tokens: int = Field(default=0, ge=0)

    # 是否允许压缩。
    # system_instruction / safety_policy 一般不允许压缩。
    compressible: bool = True

    # 是否必须保留。
    # system / safety / 当前用户问题一般必须保留。
    required: bool = False

    # 来源 ID：message_id、memory_id、tool_call_id、chunk_id 等。
    source_id: str | None = None

    metadata: dict[str, Any] = Field(default_factory=dict)


class ContextPackage(BaseModel):
    """最终上下文包。

    它不是 prompt 本身，而是 prompt 的结构化中间产物。
    """

    items: list[ContextItem]
    dropped_items: list[DroppedContextItem] = Field(default_factory=list)
    compressed_items: list[CompressedContextItem] = Field(default_factory=list)

    total_estimated_tokens: int
    max_context_tokens: int

    messages: list[dict[str, str]]

    trace: dict[str, Any] = Field(default_factory=dict)


class ContextBuildRequest(BaseModel):
    """构建上下文的请求参数。"""

    conversation_id: str
    user_message: str
    mode: Literal["chat", "agent"]

    max_context_tokens: int = Field(default_factory=get_context_context_token_by_config)

    conversation_summary: str | None = None
    conversation_state: dict[str, Any] | None = None
    recent_messages: list[dict[str, Any]] = Field(default_factory=list)

    long_term_memory_items: list[Any] = Field(default_factory=list)
    working_memory: dict[str, Any] | None = None
    tool_observations: list[dict[str, Any]] = Field(default_factory=list)
    tool_steps: list[dict[str, Any]] = Field(default_factory=list)
    multi_agent_artifacts: list[dict[str, Any]] = Field(default_factory=list)
    multi_agent_handoffs: list[dict[str, Any]] = Field(default_factory=list)

    output_requirement: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CompressedContextItem(BaseModel):
    """压缩后的上下文项。"""

    # 原上下文项 ID，便于 trace 和 audit。它不一定是 compressed_item.id，因为 compressed_item 可能是原项的修改版（如截断或摘要），
    # 但它会保留原项的 type/source/placement/priority/required/compressible 等字段。
    original_item_id: str

    # 压缩后的上下文项内容。它的 type/source/placement/priority/required/compressible 等字段通常与原项相同，
    # 但 content 和 estimated_tokens 会更新，metadata 中会增加压缩相关信息。
    compressed_item: ContextItem

    # 压缩前的 token 数。
    original_tokens: int

    # 压缩后的 token 数。注意 compressed_item.estimated_tokens 是压缩后内容的估算值，可能与 compressed_tokens 不完全一致。
    compressed_tokens: int

    # 压缩方法：head_tail（保留头尾），truncate（直接截断），llm_summary（用 LLM 生成摘要）。
    # TODO 当前只实现了 head_tail，后续可以增加其他方法。 --- IGNORE ---
    method: Literal["head_tail", "truncate", "llm_summary"]


class DroppedContextItem(BaseModel):
    """被丢弃的上下文项。"""

    item: ContextItem
    reason: Literal[
        "over_budget",
        "low_priority",
        "empty_content",
        "policy_blocked",
        "compressed_replaced",
        "type_budget_exceeded",
    ]
    detail: str | None = None
