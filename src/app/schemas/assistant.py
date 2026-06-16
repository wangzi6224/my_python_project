from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field
from src.app.config import get_agent_max_steps
from src.app.services.assistant.mode import AssistantMode, ResolvedAssistantMode


class AssistantOptions(BaseModel):
    """统一 Assistant 入口的可选参数。

    注意：这里不再出现 retrieval_mode 作为顶层 routing 参数。
    因为知识库检索已经通过 Agent tools 使用。
    """

    top_k: int = Field(default=5, ge=1, le=20)
    score_threshold: float = Field(default=0.3, ge=0, le=1)
    max_steps: int = Field(default_factory=get_agent_max_steps, ge=1, le=20)
    max_context_tokens: int | None = Field(
        default=None,
        ge=1024,
        description="可选的上下文 token 上限；实际值会按所选模型配置收紧",
    )
    enable_context_debug: bool = True

    # 预留开关：当前主要用于 auto 路由和后续 MCP。
    enable_tools: bool = True
    enable_rag_tools: bool = True
    enable_mcp_tools: bool = False

    enable_short_term_memory: bool = True
    update_conversation_state: bool = True

    enable_working_memory: bool = True
    enable_working_memory_trace: bool = True

    enable_long_term_memory: bool = True
    long_term_memory_top_k: int = Field(default=5, ge=0, le=20)
    long_term_memory_min_score: float = Field(default=0.25, ge=0, le=1)
    enable_long_term_memory_write: bool = True

    enable_multi_agent: bool = False
    multi_agent_max_rounds: int = Field(default=10, ge=1, le=20)
    enable_multi_agent_review: bool = True
    enable_multi_agent_trace: bool = True

    enable_graph_rag: bool = False


class AssistantStreamRequest(BaseModel):
    message: str = Field(..., min_length=1, description="用户当前输入")
    mode: AssistantMode = Field(default="auto", description="chat / agent / mcp / auto")
    model: str | None = None
    provider: str | None = None
    options: AssistantOptions = Field(default_factory=AssistantOptions)


class RouteDecision(BaseModel):
    mode: ResolvedAssistantMode
    reason: str
    matched_keywords: list[str] = Field(default_factory=list)


class AssistantRunCreate(BaseModel):
    conversation_id: str
    mode: ResolvedAssistantMode | AssistantMode
    input: str
    model: str | None = None
    provider: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
