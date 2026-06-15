from typing import Any

from time import perf_counter

from src.app.agent_trace_store import (
    create_agent_event,
    create_agent_run,
    create_agent_step,
    update_agent_run,
)

from src.app.config import (
    get_llm_provider_name,
    resolve_llm_model,
    get_agent_planner_type,
    resolve_max_context_tokens,
    get_agent_max_steps,
    is_agent_query_rewrite_enabled,
)
from src.app.conversation_store import (
    create_message,
    get_conversation,
    list_messages,
    update_conversation,
)
from src.app.exceptions import ConversationError
from src.app.services.agent.loop import AgentLoop
from src.app.services.agent.planner_prompt_builder import LLM_PLANNER_PROMPT_VERSION
from src.app.services.agent.prompt_builder import AgentPromptBuilder
from src.app.services.agent.query_rewrite import (
    count_user_messages,
    normalize_query_rewrite_result,
    should_rewrite_agent_query,
    skipped_query_rewrite,
)
from src.app.services.agent.state import AgentState
from src.app.services.assistant.event import EVENT_AGENT_RUN_END, EVENT_AGENT_RUN_START
from src.app.services.llm.factory import get_llm_provider
from src.app.services.observability.llm_observer import build_llm_span_metadata
from src.app.services.observability.prompt_registry import get_prompt_version
from src.app.services.observability.trace_schema import (
    SPAN_TYPE_AGENT_RUN,
    SPAN_TYPE_CONTEXT_FINAL_ASSEMBLE,
    SPAN_TYPE_LLM_CALL,
    SPAN_TYPE_QUERY_REWRITE,
    TraceSpanCreate,
)
from src.app.services.observability.span import trace_span
from src.app.services.observability.trace_store import TraceStore
from src.app.services.rag.query_rewriter import QueryRewriter
from src.app.services.tools.registry import ToolRegistry
from src.app.services.tools.list_docs import ListDocsTool
from src.app.services.tools.search_docs import SearchDocsTool
from src.app.services.tools.read_doc import ReadDocTool
from src.app.services.memory.working_memory import WorkingMemory
from src.app.services.memory.long_term_schemas import RetrievedLongTermMemory
from src.app.config import get_agent_allowed_tools, get_mcp_allowed_tools
from src.app.services.mcp.registry import McpRegistry


class AgentService:
    def __init__(self) -> None:
        self.llm_provider = get_llm_provider()
        self.prompt_builder = AgentPromptBuilder()
        self.planner_type = get_agent_planner_type()
        self.query_rewriter = QueryRewriter()

        tool_registry = ToolRegistry()
        tools_list = (
            ListDocsTool(),
            SearchDocsTool(),
            ReadDocTool(),
        )

        for tool in tools_list:
            tool_registry.register(tool)

    def chat(
        self,
        conversation_id: str,
        question: str,
        top_k: int = 5,
        score_threshold: float = 0.3,
        max_steps: int | None = None,
        model: str | None = None,
        enable_working_memory: bool = True,
        enable_mcp_tools: bool = False,
        memory_context: list[RetrievedLongTermMemory] | None = None,
        conversation_state: dict[str, Any] | None = None,
        trace_id: str | None = None,
        parent_span_id: str | None = None,
        assistant_run_id: str | None = None,
        max_context_tokens: int | None = None,
    ) -> dict[str, Any]:
        conversation = get_conversation(conversation_id)

        if conversation is None:
            raise ConversationError(
                message="会话不存在",
                detail=f"conversation_id={conversation_id}",
                status_code=404,
            )

        clean_question = question.strip()

        if not clean_question:
            raise ConversationError(
                message="问题不能为空",
                status_code=400,
            )

        resolved_max_steps = max_steps or get_agent_max_steps()

        selected_model = resolve_llm_model(
            model=model,
            stored_model=conversation.get("model"),
            stored_provider=conversation.get("provider"),
        )
        resolved_max_context_tokens = resolve_max_context_tokens(
            selected_model,
            max_context_tokens,
        )

        user_message = create_message(
            conversation_id=conversation_id,
            role="user",
            content=clean_question,
            metadata={
                "type": "agent_user_question",
            },
        )

        recent_messages = list_messages(conversation_id)[-10:]
        rewrite_required = should_rewrite_agent_query(
            question=clean_question,
            recent_messages=recent_messages,
        )

        run_start = perf_counter()

        agent_run = create_agent_run(
            conversation_id=conversation_id,
            user_message_id=user_message["id"],
            input_text=clean_question,
            model=selected_model,
            provider=get_llm_provider_name(),
            max_steps=resolved_max_steps,
            metadata={
                "top_k": top_k,
                "score_threshold": score_threshold,
                "query_rewrite": {
                    "enabled": is_agent_query_rewrite_enabled(),
                    "should_rewrite": rewrite_required,
                },
            },
        )

        run_id = agent_run["id"]

        trace_store = TraceStore()

        agent_span = None
        if trace_id and assistant_run_id:
            agent_span = trace_store.create_span(
                TraceSpanCreate(
                    trace_id=trace_id,
                    run_id=assistant_run_id,
                    parent_span_id=parent_span_id,
                    conversation_id=conversation_id,
                    assistant_run_id=assistant_run_id,
                    agent_run_id=run_id,
                    span_type=SPAN_TYPE_AGENT_RUN,
                    name="agent_loop",
                    input={
                        "question": clean_question,
                        "should_rewrite_query": rewrite_required,
                        "max_steps": resolved_max_steps,
                        "enable_mcp_tools": enable_mcp_tools,
                    },
                    metadata={
                        "planner_type": self.planner_type,
                        "model": selected_model,
                    },
                )
            )

        rewrite_input = {
            "question": clean_question,
            "recent_message_count": len(recent_messages),
            "recent_user_message_count": count_user_messages(recent_messages),
            "should_rewrite": rewrite_required,
            "enabled": is_agent_query_rewrite_enabled(),
        }

        def run_query_rewrite() -> dict[str, Any]:
            if not rewrite_required:
                return skipped_query_rewrite(
                    clean_question,
                    "SKIPPED_BY_HEURISTIC",
                )

            return self.query_rewriter.rewrite(
                conversation_summary=conversation.get("summary"),
                recent_messages=recent_messages,
                current_question=clean_question,
                model=selected_model,
                purpose="agent_planning",
            )

        if trace_id and assistant_run_id:
            with trace_span(
                trace_id=trace_id,
                run_id=assistant_run_id,
                parent_span_id=agent_span.id if agent_span else parent_span_id,
                conversation_id=conversation_id,
                assistant_run_id=assistant_run_id,
                agent_run_id=run_id,
                span_type=SPAN_TYPE_QUERY_REWRITE,
                name="agent_query_rewrite",
                input=rewrite_input,
                metadata={
                    "model": selected_model if rewrite_required else None,
                    "purpose": "agent_planning",
                },
                store=trace_store,
            ) as rewrite_span:
                rewrite_result = run_query_rewrite()
                rewrite_span.finish(
                    output=rewrite_result,
                    metadata={
                        "rewrite_changed": rewrite_result.get("rewrite_changed"),
                        "fallback_reason": rewrite_result.get("fallback_reason"),
                        "latency_ms": rewrite_result.get("latency_ms"),
                    },
                )
        else:
            rewrite_result = run_query_rewrite()

        rewritten_question, rewrite_result = normalize_query_rewrite_result(
            question=clean_question,
            rewrite_result=rewrite_result,
        )

        create_agent_event(
            run_id=run_id,
            event_type=EVENT_AGENT_RUN_START,
            payload={
                "conversation_id": conversation_id,
                "user_message_id": user_message["id"],
                "question": clean_question,
                "rewritten_question": rewritten_question,
                "query_rewrite": rewrite_result,
                "model": selected_model,
            },
        )

        serialized_memory_context = [
            item.model_dump(mode="json") for item in (memory_context or [])
        ]
        working_memory_context = (
            serialized_memory_context if enable_working_memory else []
        )
        working_memory_constraints = (
            (conversation_state or {}).get("confirmed_constraints", [])
            if enable_working_memory
            else []
        )
        working_memory_metadata = (
            {
                "conversation_state": conversation_state,
                "query_rewrite": rewrite_result,
            }
            if enable_working_memory
            else {
                "conversation_state": None,
                "query_rewrite": rewrite_result,
            }
        )

        working_memory = WorkingMemory(
            goal=clean_question,
            task_status="planning",
            memory_context=working_memory_context,
            constraints=working_memory_constraints,
            metadata=working_memory_metadata,
        )

        state = AgentState(
            run_id=run_id,
            conversation_id=conversation_id,
            user_message_id=user_message["id"],
            question=clean_question,
            original_question=clean_question,
            rewritten_question=rewritten_question,
            query_rewrite=rewrite_result,
            messages=recent_messages,
            max_steps=resolved_max_steps,
            model=selected_model,
            top_k=top_k,
            score_threshold=score_threshold,
            planner_type=self.planner_type,
            planner_prompt_version=(
                LLM_PLANNER_PROMPT_VERSION
                if self.planner_type == "llm"
                else self.planner_type
            ),
            working_memory=working_memory,
            trace_id=trace_id,
            agent_span_id=agent_span.id if agent_span else None,
            parent_span_id=parent_span_id,
            assistant_run_id=assistant_run_id,
        )

        agent_loop = AgentLoop(
            tool_registry=self._build_tool_registry(enable_mcp_tools=enable_mcp_tools),
            planner_type=self.planner_type,
        )

        try:
            state: AgentState = agent_loop.run(state)
        except Exception as exc:
            if agent_span:
                trace_store.finish_span(
                    agent_span.id,
                    status="error",
                    error_code=exc.__class__.__name__,
                    error_message=str(exc),
                )
            raise

        context_span = None
        if trace_id and assistant_run_id:
            context_span = trace_store.create_span(
                TraceSpanCreate(
                    trace_id=trace_id,
                    run_id=assistant_run_id,
                    parent_span_id=agent_span.id if agent_span else parent_span_id,
                    conversation_id=conversation_id,
                    assistant_run_id=assistant_run_id,
                    agent_run_id=run_id,
                    span_type=SPAN_TYPE_CONTEXT_FINAL_ASSEMBLE,
                    name="agent_final_context",
                    input={
                        "observation_count": len(state.observations),
                        "max_context_tokens": resolved_max_context_tokens,
                    },
                )
            )

        try:
            context_package = self.prompt_builder.build_final_context_package(
                state=state,
                conversation_summary=conversation.get("summary"),
                conversation_state=conversation_state,
                long_term_memory_items=memory_context or [],
                max_context_tokens=resolved_max_context_tokens,
            )

            if context_span:
                trace_store.finish_span(
                    context_span.id,
                    output={
                        "selected_count": len(context_package.items),
                        "dropped_count": len(context_package.dropped_items),
                        "total_estimated_tokens": context_package.total_estimated_tokens,
                        "trace": context_package.trace,
                    },
                )
        except Exception as exc:
            if context_span:
                trace_store.finish_span(
                    context_span.id,
                    status="error",
                    error_code=exc.__class__.__name__,
                    error_message=str(exc),
                )
            if agent_span:
                trace_store.finish_span(
                    agent_span.id,
                    status="error",
                    error_code=exc.__class__.__name__,
                    error_message=str(exc),
                )
            raise

        final_messages = context_package.messages

        final_answer_start = perf_counter()

        llm_span = None
        if trace_id and assistant_run_id:
            llm_span = trace_store.create_span(
                TraceSpanCreate(
                    trace_id=trace_id,
                    run_id=assistant_run_id,
                    parent_span_id=agent_span.id if agent_span else parent_span_id,
                    conversation_id=conversation_id,
                    assistant_run_id=assistant_run_id,
                    agent_run_id=run_id,
                    span_type=SPAN_TYPE_LLM_CALL,
                    name="agent_final_answer",
                    input={
                        "message_count": len(final_messages),
                    },
                    metadata={
                        "operation": "final_answer",
                        "prompt_name": "agent.final_answer",
                        "prompt_version": get_prompt_version("agent.final_answer"),
                        "model": selected_model,
                        "provider": get_llm_provider_name(),
                    },
                )
            )

        try:
            response = self.llm_provider.chat(
                messages=final_messages,
                model=selected_model,
                thinking_enabled=False,
            )

            llm_metadata = build_llm_span_metadata(
                operation="final_answer",
                prompt_name="agent.final_answer",
                model=response.model,
                provider=response.provider,
                messages=final_messages,
                completion_text=response.content,
            )

            if llm_span:
                trace_store.finish_span(
                    llm_span.id,
                    output={
                        "answer_chars": len(response.content),
                    },
                    metadata=llm_metadata,
                )
        except Exception as exc:
            if llm_span:
                trace_store.finish_span(
                    llm_span.id,
                    status="error",
                    error_code=exc.__class__.__name__,
                    error_message=str(exc),
                )
            if agent_span:
                trace_store.finish_span(
                    agent_span.id,
                    status="error",
                    error_code=exc.__class__.__name__,
                    error_message=str(exc),
                )
            raise

        final_answer_latency_ms = int((perf_counter() - final_answer_start) * 1000)

        create_agent_step(
            run_id=run_id,
            step_index=len(state.steps) + 1,
            step_type="final_answer",
            success=True,
            latency_ms=final_answer_latency_ms,
            tool_result={
                "answer": response.content,
                "model": response.model,
                "provider": response.provider,
            },
        )

        total_latency_ms = int((perf_counter() - run_start) * 1000)

        update_agent_run(
            run_id,
            status="completed",
            final_answer=response.content,
            step_count=len(state.steps) + 1,
            total_latency_ms=total_latency_ms,
        )

        create_agent_event(
            run_id=run_id,
            event_type=EVENT_AGENT_RUN_END,
            payload={
                "status": "completed",
                "step_count": len(state.steps) + 1,
                "total_latency_ms": total_latency_ms,
            },
        )

        tool_calls = [
            step.model_dump() for step in state.steps if step.type == "tool_call"
        ]

        if agent_span:
            trace_store.finish_span(
                agent_span.id,
                output={
                    "finish_reason": state.finish_reason,
                    "step_count": len(state.steps),
                    "tool_call_count": len(tool_calls),
                    "query_rewrite": rewrite_result,
                    "used_tools": [
                        step.tool_name for step in state.steps if step.tool_name
                    ],
                },
            )

        trace = {
            "run_id": run_id,
            "query_rewrite": rewrite_result,
            "max_steps": resolved_max_steps,
            "loop_step_count": len(state.steps),
            "tool_call_count": len(tool_calls),
            "used_tools": [step.tool_name for step in state.steps if step.tool_name],
            "finish_reason": state.finish_reason,
            "planner": {
                "type": state.planner_type,
                "prompt_version": state.planner_prompt_version,
                "fallback_count": state.planner_fallback_count,
                "decision_count": state.planner_decision_count,
            },
            "observations": [item.model_dump() for item in state.observations],
            "context": context_package.trace,
            "working_memory": state.working_memory.model_dump(mode="json"),
            "mcp": {
                "enabled": enable_mcp_tools,
                "used": any(
                    str(step.tool_name or "").startswith("mcp__")
                    for step in state.steps
                ),
                "tool_calls": [
                    {
                        "tool_name": step.tool_name,
                        "success": step.success,
                        "latency_ms": step.latency_ms,
                        "source": "mcp",
                    }
                    for step in state.steps
                    if str(step.tool_name or "").startswith("mcp__")
                ],
            },
            "model": response.model,
            "provider": response.provider,
        }
        trace_summary = trace_store.summarize_trace(trace_id) if trace_id else {}

        assistant_message = create_message(
            conversation_id=conversation_id,
            role="assistant",
            content=response.content,
            metadata={
                "type": "agent_answer",
                "assistant_run_id": assistant_run_id,
                "user_message_id": user_message["id"],
                "run_id": run_id,
                "tool_calls": tool_calls,
                "trace": trace,
                "trace_id": trace_id,
                "trace_summary": trace_summary,
                "model": response.model,
                "provider": response.provider,
            },
        )

        update_conversation(conversation_id, {})

        return {
            "run_id": run_id,
            "conversation_id": conversation_id,
            "user_message_id": user_message["id"],
            "assistant_message_id": assistant_message["id"],
            "question": clean_question,
            "answer": assistant_message["content"],
            "tool_calls": tool_calls,
            "context_package": context_package.model_dump(mode="json"),
            "trace": trace,
            "query_rewrite": rewrite_result,
        }

    def _build_tool_registry(self, *, enable_mcp_tools: bool) -> ToolRegistry:
        allowed_tools = get_agent_allowed_tools()

        if enable_mcp_tools:
            mcp_allowed = get_mcp_allowed_tools()
            allowed_tools = [*allowed_tools, *mcp_allowed]

        tool_registry = ToolRegistry(allowed_tools=allowed_tools)

        # 注册本地工具
        for tool in (
            ListDocsTool(),
            SearchDocsTool(),
            ReadDocTool(),
        ):
            tool_registry.register(tool)

        if enable_mcp_tools:
            # 注册 MCP 工具
            McpRegistry().register_to_tool_registry(tool_registry)

        return tool_registry
