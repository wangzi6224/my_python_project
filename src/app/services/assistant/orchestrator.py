from __future__ import annotations

from collections.abc import Iterable
from time import perf_counter
from typing import Any

from src.app.config import resolve_llm_model, resolve_max_context_tokens
from src.app.conversation_store import (
    create_message,
    get_conversation,
    list_recent_messages,
    update_conversation,
)
from src.app.logger import get_logger
from src.app.schemas.assistant import AssistantStreamRequest
from src.app.services.agent.agent_service import AgentService
from src.app.services.assistant.event import (
    EVENT_ASSISTANT_END,
    EVENT_ASSISTANT_START,
    EVENT_DELTA,
    EVENT_DONE,
    EVENT_ERROR,
    EVENT_ROUTE_DECISION,
    EVENT_TOOL_CALL_END,
    EVENT_TOOL_CALL_START,
    EVENT_LONG_TERM_MEMORY_ITEM,
    EVENT_LONG_TERM_MEMORY_RETRIEVAL_START,
    EVENT_LONG_TERM_MEMORY_WRITE,
    EVENT_SHORT_TERM_MEMORY_LOADED,
    EVENT_WORKING_MEMORY_UPDATED,
    EVENT_CONTEXT_ASSEMBLED,
    sse_event,
)
from src.app.services.assistant.llm_router import ModeRouter
from src.app.services.assistant.mode_router import RouterContext
from src.app.services.assistant.route_decision import RouteDecision
from src.app.services.assistant.run_store import AssistantRunStore
from src.app.services.llm.factory import get_llm_provider
from src.app.services.observability.llm_observer import build_llm_span_metadata
from src.app.services.observability.prompt_registry import get_prompt_version
from src.app.services.summarizer import Summarizer
from src.app.services.memory.short_term_builder import ShortTermMemoryBuilder
from src.app.services.memory.short_term_store import ShortTermMemoryStore
from src.app.services.memory.conversation_state_extractor import (
    ConversationStateExtractor,
)
from src.app.services.memory.long_term_retriever import LongTermMemoryRetriever
from src.app.services.memory.long_term_writer import LongTermMemoryWriter
from src.app.services.memory.long_term_schemas import (
    LongTermMemoryRetrievalResult,
    LongTermMemorySearchRequest,
    LongTermMemoryWriteResult,
    RetrievedLongTermMemory,
)
from src.app.services.context_engineering.context_assembler import ContextAssembler
from src.app.services.context_engineering.schemas import ContextBuildRequest
from src.app.exceptions import ConversationError
from src.app.services.observability.span import trace_span
from src.app.services.observability.trace_schema import (
    SPAN_TYPE_ASSISTANT_RUN,
    SPAN_TYPE_CONTEXT_ASSEMBLE,
    SPAN_TYPE_LLM_CALL,
    SPAN_TYPE_MEMORY_LONG_TERM_RETRIEVE,
    SPAN_TYPE_MEMORY_LONG_TERM_WRITE,
    SPAN_TYPE_MEMORY_SHORT_TERM_LOAD,
    SPAN_TYPE_ROUTER_DECISION,
    TraceSpanCreate,
)
from src.app.services.observability.trace_store import TraceStore

logger = get_logger()


class AssistantOrchestrator:
    """统一 Assistant 入口编排器。

    Week 14 Agent-first 版本：
    - mode=chat：普通多轮聊天
    - mode=agent：工具增强聊天，包括知识库检索
    - mode=auto：规则路由到 chat 或 agent

    注意：这里没有 mode=rag。
    RAG 能力通过 Agent tools 使用。
    """

    def __init__(self) -> None:
        self.mode_router = ModeRouter()
        self.run_store = AssistantRunStore()
        self.agent_service = AgentService()

        self.short_term_builder = ShortTermMemoryBuilder()
        self.short_term_store = ShortTermMemoryStore()
        self.conversation_state_extractor = ConversationStateExtractor()

        self.long_term_retriever = LongTermMemoryRetriever()
        self.long_term_writer = LongTermMemoryWriter()
        self.context_assembler = ContextAssembler()

    def stream(
        self,
        *,
        conversation_id: str,
        request: AssistantStreamRequest,
    ) -> Iterable[str]:
        start = perf_counter()
        clean_message = request.message.strip()
        # 校验部分
        if not clean_message:
            # 第一步：消息内容不能为空，直接返回错误事件并结束流。
            yield sse_event(
                EVENT_ERROR,
                {
                    "code": "EMPTY_MESSAGE",
                    "message": "消息内容不能为空",
                },
            )
            yield sse_event(EVENT_DONE, "[DONE]")
            return

        conversation = get_conversation(conversation_id)
        if conversation is None:
            # 第二步：会话不存在，直接返回错误事件并结束流。
            yield sse_event(
                EVENT_ERROR,
                {
                    "code": "CONVERSATION_NOT_FOUND",
                    "message": "会话不存在",
                    "detail": f"conversation_id={conversation_id}",
                },
            )
            yield sse_event(EVENT_DONE, "[DONE]")
            return

        # 第三步：选择模型的优先级：请求参数 > 会话历史记录 > 系统默认配置。
        selected_model = resolve_llm_model(
            model=request.model,
            stored_model=conversation.get("model"),
            stored_provider=conversation.get("provider"),
            provider=request.provider,
        )

        root_span = None

        try:
            trace_store = TraceStore()

            # 第四步：先创建 Assistant 运行记录，后续 span 统一使用 assistant_run_id 作为关联键。
            assistant_run = self.run_store.create_run(
                conversation_id=conversation_id,
                mode=request.mode,
                input_text=clean_message,
                model=selected_model,
                provider=request.provider or conversation.get("provider"),
                metadata={
                    "requested_mode": request.mode,
                    "options": request.options.model_dump(),
                },
            )
            assistant_run_id = assistant_run["id"]
            trace_id = f"trace_{assistant_run_id}"

            root_span = trace_store.create_span(
                TraceSpanCreate(
                    trace_id=trace_id,
                    run_id=assistant_run_id,
                    conversation_id=conversation_id,
                    assistant_run_id=assistant_run_id,
                    span_type=SPAN_TYPE_ASSISTANT_RUN,
                    name="assistant_stream",
                    input={
                        "message": clean_message,
                        "requested_mode": request.mode,
                        "options": request.options.model_dump(mode="json"),
                    },
                    metadata={
                        "model": selected_model,
                        "provider": request.provider or conversation.get("provider"),
                    },
                )
            )

            # 第五步：在 root span 下执行路由决策，记录路由耗时供后续分析。
            route_start = perf_counter()
            with trace_span(
                trace_id=trace_id,
                parent_span_id=root_span.id,
                run_id=assistant_run_id,
                conversation_id=conversation_id,
                assistant_run_id=assistant_run_id,
                span_type=SPAN_TYPE_ROUTER_DECISION,
                name="mode_router",
                input={
                    "message": clean_message,
                    "requested_mode": request.mode,
                },
                metadata={
                    "selected_model": selected_model,
                },
                store=trace_store,
            ) as route_span:
                route_decision = self._route(
                    conversation_id=conversation_id,
                    request=request,
                    selected_model=selected_model,
                )
                route_ms = int((perf_counter() - route_start) * 1000)
                route_span.finish(
                    output=route_decision.model_dump(mode="json"),
                    metadata={"latency_ms": route_ms},
                )
            self.run_store.update_run(
                assistant_run_id,
                status="running",
                mode=route_decision.mode,
                metadata={
                    "requested_mode": request.mode,
                    "options": request.options.model_dump(mode="json"),
                    "route_decision": route_decision.model_dump(mode="json"),
                },
            )

        except Exception as exc:
            latency_ms = int((perf_counter() - start) * 1000)
            logger.exception(
                "Assistant route/start failed: conversation_id=%s error=%s",
                conversation_id,
                exc,
            )
            if root_span is not None:
                try:
                    trace_store.finish_span(
                        root_span.id,
                        status="error",
                        error_code=exc.__class__.__name__,
                        error_message=str(exc),
                    )
                except Exception:
                    logger.exception("Failed to finish assistant root span")
            yield sse_event(
                EVENT_ERROR,
                {
                    "code": "ASSISTANT_ROUTE_ERROR",
                    "message": "Assistant 路由初始化失败",
                    "detail": str(exc),
                    "latency_ms": latency_ms,
                },
            )
            yield sse_event(EVENT_DONE, "[DONE]")
            return

        yield sse_event(
            EVENT_ASSISTANT_START,
            {
                "assistant_run_id": assistant_run_id,
                "conversation_id": conversation_id,
                "mode": route_decision.mode,
                "requested_mode": request.mode,
            },
        )

        yield sse_event(
            EVENT_ROUTE_DECISION,
            {
                "mode": route_decision.mode,
                "reason": route_decision.reason,
                "matched_keywords": route_decision.matched_keywords,
            },
        )

        short_term_memory: dict[str, Any] | None = None
        long_term_memory: LongTermMemoryRetrievalResult | None = None
        long_term_memory_items: list[RetrievedLongTermMemory] = []

        if request.options.enable_short_term_memory:
            with trace_span(
                trace_id=trace_id,
                run_id=assistant_run_id,
                parent_span_id=root_span.id,
                conversation_id=conversation_id,
                assistant_run_id=assistant_run_id,
                span_type=SPAN_TYPE_MEMORY_SHORT_TERM_LOAD,
                name="short_term_memory_load",
                input={
                    "recent_limit": 10,
                },
                store=trace_store,
            ) as short_term_span:
                # 构建短期记忆，供后续 Agent 使用。目前仅包含最近的对话消息，后续可以增加更多类型的记忆。
                short_term_memory = self.short_term_builder.build(
                    conversation_id=conversation_id,
                    recent_limit=10,
                )
                short_term_span.finish(
                    output=short_term_memory.get("trace") or {},
                )

        if (
            request.options.enable_long_term_memory
            and request.options.long_term_memory_top_k > 0
        ):
            with trace_span(
                trace_id=trace_id,
                run_id=assistant_run_id,
                parent_span_id=root_span.id,
                conversation_id=conversation_id,
                assistant_run_id=assistant_run_id,
                span_type=SPAN_TYPE_MEMORY_LONG_TERM_RETRIEVE,
                name="long_term_memory_retrieve",
                input={
                    "query": clean_message,
                    "top_k": request.options.long_term_memory_top_k,
                    "min_score": request.options.long_term_memory_min_score,
                },
                store=trace_store,
            ) as memory_span:
                # 构建长期记忆检索请求，供后续 Agent 使用。目前支持多种记忆类型的检索，后续可以增加更多选项。
                long_term_memory = self.long_term_retriever.retrieve(
                    LongTermMemorySearchRequest(
                        query=clean_message,
                        user_id="default_user",
                        top_k=request.options.long_term_memory_top_k,
                        min_score=request.options.long_term_memory_min_score,
                        memory_types=[
                            "user_profile",  # 用户画像
                            "semantic",  # 语义记忆，基于向量检索的通用记忆类型
                            "episodic",  # 事件记忆，记录用户的具体事件和经历
                            "tool_preference",  # 工具偏好记忆，记录用户对工具使用的偏好和习惯
                            "project",  # 项目记忆，记录用户参与的项目相关信息
                        ],
                    )
                )

                long_term_memory_items = long_term_memory.items
                memory_span.finish(
                    output={
                        "count": len(long_term_memory_items),
                        "latency_ms": long_term_memory.latency_ms,
                        "memorys": [
                            {
                                "id": item.item.id,
                                "workspace_id": item.item.workspace_id,
                                "importance": item.item.importance,
                                "confidence": item.item.confidence,
                            }
                            for item in long_term_memory_items
                        ],
                    },
                )

        if short_term_memory:
            # 第六步：加载短期记忆
            yield sse_event(
                EVENT_SHORT_TERM_MEMORY_LOADED,
                {
                    "conversation_id": conversation_id,
                    "has_summary": bool(short_term_memory.get("summary")),
                    "has_state": bool(short_term_memory.get("state")),
                    "recent_message_count": len(
                        short_term_memory.get("recent_messages") or []
                    ),
                },
            )

        if long_term_memory is not None:
            # 第七步：加载长期记忆，并逐条返回检索到的记忆项，供前端展示和后续分析。
            yield sse_event(
                EVENT_LONG_TERM_MEMORY_RETRIEVAL_START,
                {
                    "query": long_term_memory.query,
                    "top_k": request.options.long_term_memory_top_k,
                    "latency_ms": long_term_memory.latency_ms,
                },
            )

            for memory in long_term_memory_items:
                yield sse_event(
                    EVENT_LONG_TERM_MEMORY_ITEM,
                    {
                        "memory_id": memory.item.id,
                        "memory_type": memory.item.memory_type,
                        "score": memory.score,
                        "content": memory.item.content,
                        "importance": memory.item.importance,
                        "confidence": memory.item.confidence,
                    },
                )

        try:
            params = {
                "conversation_id": conversation_id,
                "clean_message": clean_message,
                "selected_model": selected_model,
                "assistant_run_id": assistant_run_id,
                "request": request,
                "route_decision": route_decision,
                "route_ms": route_ms,
                "start": start,
                "short_term_memory": short_term_memory,
                "long_term_memory": long_term_memory,
                "long_term_memory_items": long_term_memory_items,
            }
            if route_decision.mode == "chat":
                yield from self._stream_chat(
                    **params,
                    trace_id=trace_id,
                    root_span_id=root_span.id,
                    provider=request.provider or conversation.get("provider"),
                )
                try:
                    trace_store.finish_span(
                        root_span.id,
                        status="success",
                        output={"mode": "chat"},
                    )
                except Exception:
                    logger.exception("Failed to finish assistant root span")
                return
            if route_decision.mode == "agent":
                yield from self._stream_agent(
                    **params,
                    trace_id=trace_id,
                    root_span_id=root_span.id,
                )
                try:
                    trace_store.finish_span(
                        root_span.id,
                        status="success",
                        output={"mode": "agent"},
                    )
                except Exception:
                    logger.exception("Failed to finish assistant root span")
                return

            raise RuntimeError(f"不支持的 Assistant 模式: {route_decision.mode}")

        except Exception as exc:
            latency_ms = int((perf_counter() - start) * 1000)
            logger.exception(
                "Assistant stream failed: conversation_id=%s run_id=%s error=%s",
                conversation_id,
                assistant_run_id,
                exc,
            )

            self.run_store.update_run(
                assistant_run_id,
                status="failed",
                latency_ms=latency_ms,
                trace={
                    "error": {
                        "code": "ASSISTANT_STREAM_ERROR",
                        "message": str(exc),
                    },
                    "route_decision": route_decision.model_dump(),
                    "latency": {
                        "route_ms": route_ms,
                        "agent_ms": None,
                        "total_ms": latency_ms,
                    },
                },
            )
            try:
                trace_store.finish_span(
                    root_span.id,
                    status="error",
                    error_code=exc.__class__.__name__,
                    error_message=str(exc),
                )
            except Exception:
                logger.exception("Failed to finish assistant root span")

            yield sse_event(
                EVENT_ERROR,
                {
                    "code": "ASSISTANT_STREAM_ERROR",
                    "message": "Assistant 处理失败",
                    "detail": str(exc),
                },
            )
            yield sse_event(EVENT_DONE, "[DONE]")

    def debug_context(
        self,
        *,
        conversation_id: str,
        request: AssistantStreamRequest,
    ) -> dict[str, Any]:
        conversation = get_conversation(conversation_id)
        if conversation is None:
            raise ConversationError(
                message="会话不存在",
                detail=f"conversation_id={conversation_id}",
                status_code=404,
            )

        short_term_memory = None
        if request.options.enable_short_term_memory:
            short_term_memory = self.short_term_builder.build(
                conversation_id=conversation_id,
                recent_limit=10,
            )

        long_term_memory_items = []
        if (
            request.options.enable_long_term_memory
            and request.options.long_term_memory_top_k > 0
        ):
            long_term_memory = self.long_term_retriever.retrieve(
                LongTermMemorySearchRequest(
                    query=request.message,
                    user_id="default_user",
                    top_k=request.options.long_term_memory_top_k,
                    min_score=request.options.long_term_memory_min_score,
                )
            )
            long_term_memory_items = long_term_memory.items

        selected_model = resolve_llm_model(
            model=request.model,
            stored_model=conversation.get("model"),
            stored_provider=conversation.get("provider"),
            provider=request.provider,
        )
        max_context_tokens = resolve_max_context_tokens(
            selected_model,
            request.options.max_context_tokens,
        )

        route_decision = self._route(
            conversation_id=conversation_id,
            request=request,
            selected_model=selected_model,
        )

        context_package = ContextAssembler().build(
            ContextBuildRequest(
                conversation_id=conversation_id,
                user_message=request.message,
                mode="agent" if route_decision.mode == "agent" else "chat",
                conversation_summary=conversation.get("summary"),
                conversation_state=(
                    short_term_memory.get("state") if short_term_memory else None
                ),
                recent_messages=list_recent_messages(conversation_id, limit=10),
                long_term_memory_items=long_term_memory_items,
                max_context_tokens=max_context_tokens,
            )
        )

        return context_package.model_dump(mode="json")

    def _stream_chat(
        self,
        *,
        conversation_id: str,
        clean_message: str,
        selected_model: str,
        provider: str | None,
        assistant_run_id: str,
        request: AssistantStreamRequest,
        route_decision: RouteDecision,
        route_ms: int,
        start: float,
        trace_id: str,
        root_span_id: str,
        short_term_memory: dict[str, Any] | None,
        long_term_memory: LongTermMemoryRetrievalResult | None,
        long_term_memory_items: list[RetrievedLongTermMemory],
    ) -> Iterable[str]:
        trace_store = TraceStore()

        user_message = create_message(
            conversation_id=conversation_id,
            role="user",
            content=clean_message,
            metadata={
                "type": "assistant_user_message",
                "assistant_run_id": assistant_run_id,
                "mode": "chat",
            },
        )

        with trace_span(
            trace_id=trace_id,
            run_id=assistant_run_id,
            parent_span_id=root_span_id,
            conversation_id=conversation_id,
            assistant_run_id=assistant_run_id,
            span_type=SPAN_TYPE_CONTEXT_ASSEMBLE,
            name="chat_context_assemble",
            input={
                "mode": "chat",
                "max_context_tokens": request.options.max_context_tokens,
            },
            store=trace_store,
        ) as context_span:
            context_package = self.context_assembler.build(
                ContextBuildRequest(
                    conversation_id=conversation_id,
                    user_message=clean_message,
                    mode="chat",
                    conversation_summary=(
                        short_term_memory.get("summary") if short_term_memory else None
                    ),
                    conversation_state=(
                        short_term_memory.get("state") if short_term_memory else None
                    ),
                    recent_messages=list_recent_messages(conversation_id, limit=10),
                    long_term_memory_items=long_term_memory_items,
                    max_context_tokens=resolve_max_context_tokens(
                        selected_model,
                        request.options.max_context_tokens,
                    ),
                )
            )

            context_span.finish(
                output={
                    "selected_count": len(context_package.items),
                    "dropped_count": len(context_package.dropped_items),
                    "total_estimated_tokens": context_package.total_estimated_tokens,
                    "trace": context_package.trace,
                },
            )

        llm_messages = context_package.messages

        yield sse_event(
            EVENT_CONTEXT_ASSEMBLED,
            {
                "total_estimated_tokens": context_package.total_estimated_tokens,
                "max_context_tokens": context_package.max_context_tokens,
                "selected_count": len(context_package.items),
                "dropped_count": len(context_package.dropped_items),
            },
        )

        with trace_span(
            trace_id=trace_id,
            run_id=assistant_run_id,
            parent_span_id=root_span_id,
            conversation_id=conversation_id,
            assistant_run_id=assistant_run_id,
            span_type=SPAN_TYPE_LLM_CALL,
            name="chat_stream",
            input={
                "message_count": len(llm_messages),
            },
            metadata={
                "operation": "chat",
                "prompt_name": "assistant.chat",
                "prompt_version": get_prompt_version("assistant.chat"),
                "model": selected_model,
                "provider": provider,
            },
            store=trace_store,
        ) as llm_span:
            llm_provider = get_llm_provider(provider)
            full_answer_parts: list[str] = []
            try:
                for chunk in llm_provider.stream_chat(
                    message=llm_messages,
                    model=selected_model,
                    thinking_enabled=True,
                ):
                    if chunk.done:
                        break

                    full_answer_parts.append(chunk.delta)
                    yield sse_event(EVENT_DELTA, {"delta": chunk.delta})

                full_answer = "".join(full_answer_parts)

                llm_metadata = build_llm_span_metadata(
                    operation="chat",
                    prompt_name="assistant.chat",
                    model=selected_model,
                    provider=provider or "unknown",
                    messages=llm_messages,
                    completion_text=full_answer,
                )

                llm_span.finish(
                    output={
                        "answer_chars": len(full_answer),
                    },
                    metadata=llm_metadata,
                )
            except Exception as exc:
                llm_span.finish(
                    status="error",
                    error_code="LLM_STREAM_FAILED",
                    error_message=str(exc),
                )
                raise

        latency_ms = int((perf_counter() - start) * 1000)

        conversation_state_write = None
        long_term_memory_write = None

        if request.options.update_conversation_state:

            conversation_state_write = self._write_conversation_state_from_turn(
                conversation_id=conversation_id,
                user_message=clean_message,
                assistant_answer=full_answer,
                previous_state=(
                    short_term_memory.get("state") if short_term_memory else None
                ),
                model=selected_model,
            )

        if (
            request.options.enable_long_term_memory
            and request.options.enable_long_term_memory_write
        ):
            with trace_span(
                trace_id=trace_id,
                run_id=assistant_run_id,
                parent_span_id=root_span_id,
                conversation_id=conversation_id,
                assistant_run_id=assistant_run_id,
                span_type=SPAN_TYPE_MEMORY_LONG_TERM_WRITE,
                name="chat_long_term_memory_write",
                input={
                    "source_message_id": user_message["id"],
                },
                store=trace_store,
            ) as memory_write_span:
                long_term_memory_write = self.long_term_writer.write_from_turn(
                    user_message=clean_message,
                    assistant_answer=full_answer,
                    conversation_id=conversation_id,
                    source_message_id=user_message["id"],
                    source_run_id=assistant_run_id,
                    model=selected_model,
                )
                memory_write_span.finish(
                    output=long_term_memory_write.trace,
                )
            yield sse_event(
                EVENT_LONG_TERM_MEMORY_WRITE,
                long_term_memory_write.trace,
            )

        trace = {
            "route_decision": route_decision.model_dump(),
            "planner": {
                "type": None,
                "prompt_version": None,
                "fallback_count": 0,
                "decision_count": 0,
            },
            "agent_run_id": None,
            "tool_calls": [],
            "finish_reason": "chat_completed",
            "latency": {
                "route_ms": route_ms,
                "agent_ms": 0,
                "total_ms": latency_ms,
            },
            "context_message_count": len(llm_messages),
            "context": context_package.trace,
            "memory": {
                "short_term": self._build_short_term_memory_trace(
                    enabled=request.options.enable_short_term_memory,
                    short_term_memory=short_term_memory,
                    conversation_state_write=conversation_state_write,
                ),
                "working": self._build_working_memory_trace(
                    enabled=request.options.enable_working_memory,
                    working_memory=None,
                ),
                "long_term": self._build_long_term_memory_trace(
                    enabled=request.options.enable_long_term_memory,
                    long_term_memory=long_term_memory,
                    long_term_memory_write=long_term_memory_write,
                ),
            },
        }
        trace_summary = trace_store.summarize_trace(trace_id)

        assistant_message = create_message(
            conversation_id=conversation_id,
            role="assistant",
            content=full_answer,
            metadata={
                "type": "assistant_answer",
                "assistant_run_id": assistant_run_id,
                "mode": "chat",
                "model": selected_model,
                "provider": llm_provider.name,
                "latency_ms": latency_ms,
                "context_message_count": len(llm_messages),
                "is_stream": True,
                "tool_calls": [],
                "trace": trace,
                "trace_id": trace_id,
                "trace_summary": trace_summary,
            },
        )

        self._try_update_summary(conversation_id, model=selected_model)

        update_conversation(
            conversation_id,
            {
                "model": selected_model,
                "provider": llm_provider.name,
            },
        )

        self.run_store.update_run(
            assistant_run_id,
            status="completed",
            user_message_id=user_message["id"],
            assistant_message_id=assistant_message["id"],
            final_answer=full_answer,
            model=selected_model,
            provider=llm_provider.name,
            latency_ms=latency_ms,
            trace=trace,
        )

        yield sse_event(
            EVENT_ASSISTANT_END,
            {
                "assistant_run_id": assistant_run_id,
                "assistant_message_id": assistant_message["id"],
                "mode": "chat",
                "latency_ms": latency_ms,
                "model": selected_model,
                "provider": llm_provider.name,
                "tool_calls": [],
                "trace": trace,
                "trace_id": trace_id,
                "trace_summary": trace_summary,
            },
        )
        yield sse_event(EVENT_DONE, "[DONE]")

    def _route(
        self,
        *,
        conversation_id: str,
        request: AssistantStreamRequest,
        selected_model: str,
    ) -> RouteDecision:
        if request.mode != "auto":
            return self._normalize_route_decision(
                RouteDecision(
                    mode=request.mode,
                    confidence=1.0,
                    source="rule",
                    reason="用户显式指定 Assistant 模式",
                )
            )

        recent_messages = list_recent_messages(conversation_id, limit=6)
        context = RouterContext(
            conversation_id=conversation_id,
            message=request.message,
            recent_messages=recent_messages,
            options=request.options.model_dump(),
        )
        return self._normalize_route_decision(
            self.mode_router.route(context, model=selected_model)
        )

    def _normalize_route_decision(self, decision: RouteDecision) -> RouteDecision:
        if decision.mode == "mcp":
            return decision.model_copy(
                update={
                    "mode": "agent",
                    "reason": f"{decision.reason}；mcp 已通过 Agent tools 执行",
                }
            )

        return decision

    def _stream_agent(
        self,
        *,
        conversation_id: str,
        clean_message: str,
        selected_model: str,
        assistant_run_id: str,
        request: AssistantStreamRequest,
        route_decision: RouteDecision,
        route_ms: int,
        start: float,
        trace_id: str,
        root_span_id: str,
        short_term_memory: dict[str, Any] | None,
        long_term_memory: LongTermMemoryRetrievalResult | None,
        long_term_memory_items: list[RetrievedLongTermMemory],
    ) -> Iterable[str]:
        # 当前 AgentService.chat 是同步执行。
        agent_start = perf_counter()
        result = self.agent_service.chat(
            conversation_id=conversation_id,
            question=clean_message,
            top_k=request.options.top_k,
            score_threshold=request.options.score_threshold,
            max_steps=request.options.max_steps,
            model=selected_model,
            enable_working_memory=request.options.enable_working_memory,
            enable_mcp_tools=request.options.enable_mcp_tools,
            trace_id=trace_id,
            parent_span_id=root_span_id,
            assistant_run_id=assistant_run_id,
            max_context_tokens=resolve_max_context_tokens(
                selected_model,
                request.options.max_context_tokens,
            ),
            memory_context=(
                long_term_memory_items if request.options.enable_working_memory else []
            ),
            conversation_state=(
                short_term_memory.get("state")
                if request.options.enable_working_memory and short_term_memory
                else None
            ),
        )
        agent_ms = int((perf_counter() - agent_start) * 1000)

        tool_calls: list[dict[str, Any]] = result.get("tool_calls", [])
        trace: dict[str, Any] = result.get("trace", {})
        answer: str = result.get("answer", "")
        agent_run_id: str | None = result.get("run_id")
        user_message_id: str | None = result.get("user_message_id")
        assistant_message_id: str | None = result.get("assistant_message_id")
        trace_store = TraceStore()

        conversation_state_write = None
        long_term_memory_write = None

        if request.options.update_conversation_state:
            conversation_state_write = self._write_conversation_state_from_turn(
                conversation_id=conversation_id,
                user_message=clean_message,
                assistant_answer=answer,
                previous_state=(
                    short_term_memory.get("state") if short_term_memory else None
                ),
                model=selected_model,
            )

        if (
            request.options.enable_long_term_memory
            and request.options.enable_long_term_memory_write
        ):
            with trace_span(
                trace_id=trace_id,
                run_id=assistant_run_id,
                parent_span_id=root_span_id,
                conversation_id=conversation_id,
                assistant_run_id=assistant_run_id,
                agent_run_id=agent_run_id,
                span_type=SPAN_TYPE_MEMORY_LONG_TERM_WRITE,
                name="agent_long_term_memory_write",
                input={
                    "source_message_id": user_message_id,
                },
                store=trace_store,
            ) as memory_write_span:
                long_term_memory_write = self.long_term_writer.write_from_turn(
                    user_message=clean_message,
                    assistant_answer=answer,
                    conversation_id=conversation_id,
                    source_message_id=user_message_id,
                    source_run_id=assistant_run_id,
                    model=selected_model,
                )
                memory_write_span.finish(
                    output=long_term_memory_write.trace,
                )
            yield sse_event(
                EVENT_LONG_TERM_MEMORY_WRITE,
                long_term_memory_write.trace,
            )

        working_memory = trace.get("working_memory")
        if request.options.enable_working_memory_trace and working_memory is not None:
            yield sse_event(
                EVENT_WORKING_MEMORY_UPDATED,
                working_memory,
            )

        for tool_call in tool_calls:
            yield sse_event(
                EVENT_TOOL_CALL_START,
                {
                    "tool_name": tool_call.get("tool_name"),
                    "arguments": tool_call.get("arguments") or {},
                    "reason": tool_call.get("reason"),
                    "step": tool_call.get("step"),
                },
            )
            yield sse_event(
                EVENT_TOOL_CALL_END,
                {
                    "tool_name": tool_call.get("tool_name"),
                    "success": tool_call.get("success"),
                    "latency_ms": tool_call.get("latency_ms"),
                    "step": tool_call.get("step"),
                    "error_code": tool_call.get("error_code"),
                    "error_message": tool_call.get("error_message"),
                },
            )

        # 第一版可以一次性返回完整答案。
        # 后续再把 Agent final answer 改成真正 token 流。
        yield sse_event(EVENT_DELTA, {"delta": answer})

        latency_ms = int((perf_counter() - start) * 1000)

        # 从 tool_calls 中兼容性抽取 sources（第一版）
        sources: list[dict[str, Any]] = self._extract_sources_from_tool_calls(
            tool_calls
        )

        assistant_trace: dict[str, Any] = {
            "route_decision": route_decision.model_dump(),
            "planner": self._normalize_planner_trace(trace.get("planner")),
            "agent_run_id": agent_run_id,
            "tool_calls": self._summarize_tool_calls(tool_calls),
            "finish_reason": trace.get("finish_reason"),
            "latency": {
                "route_ms": route_ms,
                "agent_ms": agent_ms,
                "total_ms": latency_ms,
            },
            "context": trace.get("context"),
            "mcp": trace.get("mcp"),
            "memory": {
                "short_term": self._build_short_term_memory_trace(
                    enabled=request.options.enable_short_term_memory,
                    short_term_memory=short_term_memory,
                    conversation_state_write=conversation_state_write,
                ),
                "working": self._build_working_memory_trace(
                    enabled=request.options.enable_working_memory,
                    working_memory=(
                        working_memory
                        if request.options.enable_working_memory_trace
                        else None
                    ),
                ),
                "long_term": self._build_long_term_memory_trace(
                    enabled=request.options.enable_long_term_memory,
                    long_term_memory=long_term_memory,
                    long_term_memory_write=long_term_memory_write,
                ),
            },
        }
        trace_summary = trace_store.summarize_trace(trace_id)

        self.run_store.update_run(
            assistant_run_id,
            status="completed",
            user_message_id=user_message_id,
            assistant_message_id=assistant_message_id,
            final_answer=answer,
            model=trace.get("model") or selected_model,
            provider=trace.get("provider"),
            latency_ms=latency_ms,
            trace=assistant_trace,
            metadata={
                "agent_run_id": agent_run_id,
                "tool_call_count": len(tool_calls),
                "trace_id": trace_id,
                "trace_summary": trace_summary,
            },
        )

        yield sse_event(
            EVENT_ASSISTANT_END,
            {
                "assistant_run_id": assistant_run_id,
                "assistant_message_id": assistant_message_id,
                "agent_run_id": agent_run_id,
                "mode": "agent",
                "latency_ms": latency_ms,
                "model": trace.get("model") or selected_model,
                "provider": trace.get("provider"),
                "tool_calls": tool_calls,
                "sources": sources,
                "trace": assistant_trace,
                "trace_id": trace_id,
                "trace_summary": trace_summary,
            },
        )
        yield sse_event(EVENT_DONE, "[DONE]")

    def _write_conversation_state_from_turn(
        self,
        *,
        conversation_id: str,
        user_message: str,
        assistant_answer: str,
        previous_state: dict[str, Any] | None,
        model: str | None,
    ) -> dict[str, Any]:
        state_patch = self.conversation_state_extractor.extract(
            user_message=user_message,
            assistant_answer=assistant_answer,
            previous_state=previous_state,
            model=model,
        )

        conversation_state = self.short_term_store.upsert_state(
            conversation_id=conversation_id,
            patch=state_patch,
        )

        return conversation_state.model_dump(mode="json")

    def _build_short_term_memory_trace(
        self,
        *,
        enabled: bool,
        short_term_memory: dict[str, Any] | None,
        conversation_state_write: dict[str, Any] | None,
    ) -> dict[str, Any]:
        return {
            "enabled": enabled,
            "loaded": short_term_memory.get("trace") if short_term_memory else None,
            "state": short_term_memory.get("state") if short_term_memory else None,
            "write": conversation_state_write,
        }

    def _build_working_memory_trace(
        self,
        *,
        enabled: bool,
        working_memory: dict[str, Any] | None,
    ) -> dict[str, Any]:
        return {
            "enabled": enabled,
            "trace_enabled": enabled and bool(working_memory),
            "state": working_memory,
        }

    def _build_long_term_memory_trace(
        self,
        *,
        enabled: bool,
        long_term_memory: LongTermMemoryRetrievalResult | None,
        long_term_memory_write: LongTermMemoryWriteResult | None,
    ) -> dict[str, Any]:
        return {
            "enabled": enabled,
            "retrieval": long_term_memory.trace if long_term_memory else None,
            "items": (
                [
                    {
                        "id": item.item.id,
                        "type": item.item.memory_type,
                        "score": item.score,
                        "content": item.item.content,
                        "importance": item.item.importance,
                        "confidence": item.item.confidence,
                    }
                    for item in long_term_memory.items
                ]
                if long_term_memory
                else []
            ),
            "write": long_term_memory_write.trace if long_term_memory_write else None,
        }

    def _try_update_summary(
        self, conversation_id: str, model: str | None = None
    ) -> None:
        try:
            summarizer = Summarizer()
            if summarizer.should_update(conversation_id):
                summarizer.summarize(conversation_id=conversation_id, model=model)
        except Exception as exc:
            logger.exception(
                "Assistant 自动更新摘要失败: conversation_id=%s error=%s",
                conversation_id,
                exc,
            )

    def _extract_sources_from_tool_calls(
        self,
        tool_calls: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """从 Agent tool_calls 中兼容性抽取 sources，供前端展示与后续 Eval 使用。

        抽取原则：
        - 优先级：result.data.items / result.data.chunks / result.data.sources
        → result.items / result.chunks / result.sources → result.data
        - 字段缺失时跳过，不抛异常。
        - 同一 chunk_id 去重。
        - content_preview 截断至 160 字。
        """
        seen_chunk_ids: set[str] = set()
        sources: list[dict[str, Any]] = []

        for tool_call in tool_calls:
            result_raw = tool_call.get("result")
            if not isinstance(result_raw, dict):
                # tool_result 有时是 AgentStep 序列化后的结构
                result_raw = tool_call.get("tool_result")
            if not isinstance(result_raw, dict):
                continue

            # 尝试多个候选位置，按优先级依次查找 item 列表
            candidate_lists: list[Any] = []
            data = result_raw.get("data")
            if isinstance(data, dict):
                for key in ("items", "chunks", "sources"):
                    v = data.get(key)
                    if isinstance(v, list):
                        candidate_lists.append(v)
                        break  # 找到即止
            for key in ("items", "chunks", "sources"):
                v = result_raw.get(key)
                if isinstance(v, list):
                    candidate_lists.append(v)
                    break

            for item_list in candidate_lists:
                for item in item_list:
                    if not isinstance(item, dict):
                        continue

                    chunk_id: str | None = item.get("chunk_id") or item.get("id")
                    # 去重
                    if chunk_id and chunk_id in seen_chunk_ids:
                        continue
                    if chunk_id:
                        seen_chunk_ids.add(chunk_id)

                    # content_preview：截断至 160 字
                    content: str = (
                        item.get("content") or item.get("content_preview") or ""
                    )
                    preview: str = content[:160] if content else ""

                    source: dict[str, Any] = {
                        "chunk_id": chunk_id,
                        "document_id": item.get("document_id"),
                        "filename": item.get("filename"),
                        "heading": item.get("heading"),
                        "score": item.get("score")
                        or item.get("rrf_score")
                        or item.get("rerank_score"),
                        "distance": item.get("distance"),
                        "rerank_score": item.get("rerank_score"),
                        "rrf_score": item.get("rrf_score"),
                        "chunk_index": item.get("chunk_index"),
                        "content_preview": preview,
                    }
                    sources.append(source)

        return sources

    def _summarize_tool_calls(
        self,
        tool_calls: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return [
            {
                "step": tool_call.get("step"),
                "tool_name": tool_call.get("tool_name"),
                "success": tool_call.get("success"),
                "latency_ms": tool_call.get("latency_ms"),
            }
            for tool_call in tool_calls
        ]

    def _normalize_planner_trace(self, planner: Any) -> dict[str, Any]:
        if not isinstance(planner, dict):
            return {
                "type": None,
                "prompt_version": None,
                "fallback_count": 0,
                "decision_count": 0,
            }

        return {
            "type": planner.get("type"),
            "prompt_version": planner.get("prompt_version"),
            "fallback_count": int(planner.get("fallback_count") or 0),
            "decision_count": int(planner.get("decision_count") or 0),
        }
