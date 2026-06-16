from __future__ import annotations

from time import perf_counter
from typing import Any, cast

from src.app.config import (
    resolve_llm_model,
    resolve_max_context_tokens,
    get_llm_provider_name,
)
from src.app.conversation_store import create_message, get_conversation, list_messages
from src.app.exceptions import ConversationError
from src.app.services.context_engineering.context_assembler import ContextAssembler
from src.app.services.context_engineering.schemas import ContextBuildRequest
from src.app.services.llm.factory import get_llm_provider
from src.app.services.multi_agent.agents.coding_agent import CodingAgent
from src.app.services.multi_agent.agents.research_agent import ResearchAgent
from src.app.services.multi_agent.agents.review_agent import ReviewAgent
from src.app.services.multi_agent.agents.supervisor_agent import SupervisorAgent
from src.app.services.multi_agent.artifact_formatter import MultiAgentArtifactFormatter
from src.app.services.multi_agent.handoff import HandoffBuilder
from src.app.services.multi_agent.schemas import (
    MultiAgentConfig,
    MultiAgentResult,
    TaskPlan,
)
from src.app.services.multi_agent.state import MultiAgentState
from src.app.services.multi_agent.store import MultiAgentStore


class MultiAgentService:
    def __init__(self) -> None:
        self.store = MultiAgentStore()
        self.supervisor = SupervisorAgent()
        self.research = ResearchAgent()
        self.coding = CodingAgent()
        self.review = ReviewAgent()
        self.handoff_builder = HandoffBuilder()
        self.formatter = MultiAgentArtifactFormatter()
        self.context_assembler = ContextAssembler()
        self.llm_provider = get_llm_provider()

    def chat(
        self,
        *,
        conversation_id: str,
        question: str,
        top_k: int,
        score_threshold: float,
        max_steps: int,
        model: str | None,
        enable_mcp_tools: bool,
        trace_id: str | None,
        parent_span_id: str | None,
        assistant_run_id: str | None,
        max_context_tokens: int | None,
        memory_context: list[Any] | None,
        conversation_state: dict[str, Any] | None,
        config: MultiAgentConfig | None = None,
    ) -> dict[str, Any]:
        start = perf_counter()
        conversation = get_conversation(conversation_id)
        if conversation is None:
            raise ConversationError(
                message="会话不存在",
                detail=f"conversation_id={conversation_id}",
                status_code=404,
            )

        clean_question = question.strip()
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
            metadata={"type": "multi_agent_user_question"},
        )

        run = self.store.create_run(
            conversation_id=conversation_id,
            assistant_run_id=assistant_run_id,
            user_message_id=user_message["id"],
            input_text=clean_question,
            model=selected_model,
            provider=get_llm_provider_name(),
            metadata={"enable_mcp_tools": enable_mcp_tools},
        )

        state = MultiAgentState(
            run_id=run["id"],
            conversation_id=conversation_id,
            user_message_id=user_message["id"],
            question=clean_question,
            model=selected_model,
            config=config
            or MultiAgentConfig(
                enabled=True,
                max_role_steps=max_steps,
                enable_mcp_tools=enable_mcp_tools,
            ),
            trace_id=trace_id,
            assistant_run_id=assistant_run_id,
            parent_span_id=parent_span_id,
        )

        constraints = [
            "不新增 mode=multi_agent",
            "不新增 /multi-agent/chat 主入口",
            "不依赖 Week22 GraphRAG",
            "必须复用 AssistantOrchestrator / ContextAssembler / Trace / Eval",
        ]

        try:
            supervisor_result = self.supervisor.run_with_timing(
                question=clean_question,
                constraints=constraints,
                model=selected_model,
            )
            self._accept_role_result(state, supervisor_result)
            state.task_plan = cast(
                TaskPlan | None,
                supervisor_result.artifact and supervisor_result.artifact.data
            )

            if supervisor_result.artifact:
                self.store.create_artifact(
                    supervisor_result.artifact, multi_agent_run_id=state.run_id
                )

            research_result = self.research.run_with_timing(
                question=clean_question,
                top_k=top_k,
                score_threshold=score_threshold,
                enable_mcp_tools=enable_mcp_tools,
                model=selected_model,
            )
            self._accept_role_result(state, research_result)
            if research_result.artifact:
                self.store.create_artifact(
                    research_result.artifact, multi_agent_run_id=state.run_id
                )

            research_artifact = cast(Any, research_result.artifact)
            research_to_coding = self.handoff_builder.build(
                from_role="research",
                to_role="coding",
                artifact=research_artifact,
                task_id="coding",
                constraints=constraints,
            )
            state.add_handoff(research_to_coding)
            self.store.create_handoff(
                research_to_coding, multi_agent_run_id=state.run_id
            )

            coding_result = self.coding.run_with_timing(
                question=clean_question,
                research_artifact=research_artifact,
                constraints=constraints,
                model=selected_model,
            )
            self._accept_role_result(state, coding_result)
            if coding_result.artifact:
                self.store.create_artifact(
                    coding_result.artifact, multi_agent_run_id=state.run_id
                )

            coding_artifact = cast(Any, coding_result.artifact)
            coding_to_review = self.handoff_builder.build(
                from_role="coding",
                to_role="review",
                artifact=coding_artifact,
                task_id="review",
                constraints=constraints,
            )
            state.add_handoff(coding_to_review)
            self.store.create_handoff(coding_to_review, multi_agent_run_id=state.run_id)

            review_result = self.review.run_with_timing(
                question=clean_question,
                research_artifact=research_artifact,
                coding_artifact=coding_artifact,
                constraints=constraints,
                model=selected_model,
            )
            self._accept_role_result(state, review_result)
            if review_result.artifact:
                self.store.create_artifact(
                    review_result.artifact, multi_agent_run_id=state.run_id
                )

            answer = self._final_answer_with_context(
                state=state,
                conversation_summary=conversation.get("summary"),
                conversation_state=conversation_state,
                recent_messages=list_messages(conversation_id)[-10:],
                long_term_memory_items=memory_context or [],
                max_context_tokens=resolved_max_context_tokens,
                model=selected_model,
            )

            assistant_message = create_message(
                conversation_id=conversation_id,
                role="assistant",
                content=answer,
                metadata={
                    "type": "multi_agent_answer",
                    "assistant_run_id": assistant_run_id,
                    "run_id": state.run_id,
                    "multi_agent": self._trace(state),
                    "trace_id": trace_id,
                },
            )

            latency_ms = int((perf_counter() - start) * 1000)
            self.store.update_run(
                state.run_id,
                status="completed",
                final_answer=answer,
                assistant_message_id=assistant_message["id"],
                supervisor_plan=state.artifacts[0].data if state.artifacts else {},
                enabled_roles=cast(list[str], state.roles_used),
                finish_reason="completed",
                latency_ms=latency_ms,
            )

            trace = self._trace(state)
            return MultiAgentResult(
                run_id=state.run_id,
                conversation_id=conversation_id,
                user_message_id=user_message["id"],
                assistant_message_id=assistant_message["id"],
                answer=answer,
                status="completed",
                roles_used=state.roles_used,
                artifacts=state.artifacts,
                handoffs=state.handoffs,
                tool_calls=state.tool_calls,
                trace=trace,
                latency_ms=latency_ms,
            ).model_dump(mode="json")

        except Exception as exc:
            self.store.update_run(
                state.run_id,
                status="failed",
                finish_reason=exc.__class__.__name__,
                metadata={"error_message": str(exc)},
            )
            raise

    def _accept_role_result(self, state: MultiAgentState, result: Any) -> None:
        if result.artifact:
            state.add_artifact(result.artifact)
        normalized_tool_calls: list[dict[str, Any]] = []
        for tool_call in (result.trace or {}).get("tool_calls", []):
            metadata = dict(tool_call.get("metadata") or {})
            metadata.setdefault("role", result.role)
            metadata.setdefault("multi_agent_run_id", state.run_id)
            normalized_tool_call = {
                **tool_call,
                "role": tool_call.get("role") or result.role,
                "multi_agent_run_id": state.run_id,
                "metadata": metadata,
            }
            state.tool_calls.append(normalized_tool_call)
            normalized_tool_calls.append(normalized_tool_call)

        state.role_runs.append(
            {
                "role": result.role,
                "status": result.status,
                "latency_ms": result.latency_ms,
                "error_code": result.error_code,
                "error_message": result.error_message,
                "artifact": (
                    result.artifact.model_dump(mode="json")
                    if result.artifact
                    else None
                ),
                "trace": result.trace or {},
                "tool_calls": normalized_tool_calls,
            }
        )

    def _final_answer_with_context(
        self,
        *,
        state: MultiAgentState,
        conversation_summary: str | None,
        conversation_state: dict[str, Any] | None,
        recent_messages: list[dict[str, Any]],
        long_term_memory_items: list[Any],
        max_context_tokens: int,
        model: str | None,
    ) -> str:
        multi_agent_artifacts = [
            artifact.model_dump(mode="json") for artifact in state.artifacts
        ]
        multi_agent_handoffs = [
            handoff.model_dump(mode="json") for handoff in state.handoffs
        ]

        context_package = self.context_assembler.build(
            ContextBuildRequest(
                conversation_id=state.conversation_id,
                user_message=state.question,
                mode="agent",
                conversation_summary=conversation_summary,
                conversation_state=conversation_state,
                recent_messages=recent_messages,
                long_term_memory_items=long_term_memory_items,
                multi_agent_artifacts=multi_agent_artifacts,
                multi_agent_handoffs=multi_agent_handoffs,
                output_requirement=(
                    "请基于多智能体产物、工具资料和上下文回答用户问题。"
                    "必须体现 Research / Coding / Review 的结论，不能编造资料。"
                ),
                max_context_tokens=max_context_tokens,
            )
        )

        response = self.llm_provider.chat(
            messages=context_package.messages,
            model=model,
            thinking_enabled=False,
        )
        state.metadata["context"] = context_package.trace
        state.metadata["context_package"] = context_package.model_dump(mode="json")
        return response.content

    def _trace(self, state: MultiAgentState) -> dict[str, Any]:
        return {
            "enabled": True,
            "run_id": state.run_id,
            "roles_used": state.roles_used,
            "artifact_count": len(state.artifacts),
            "handoff_count": len(state.handoffs),
            "role_runs": self._build_role_runs(state),
            "artifacts": [item.model_dump(mode="json") for item in state.artifacts],
            "handoffs": [item.model_dump(mode="json") for item in state.handoffs],
            "tool_calls": state.tool_calls,
            "review_decision": self._extract_review_decision(state),
            "context": state.metadata.get("context"),
        }

    def _build_role_runs(self, state: MultiAgentState) -> list[dict[str, Any]]:
        handoffs = [item.model_dump(mode="json") for item in state.handoffs]
        role_runs: list[dict[str, Any]] = []

        for role_run in state.role_runs:
            role = role_run.get("role")
            role_runs.append(
                {
                    **role_run,
                    "handoffs": {
                        "incoming": [
                            item for item in handoffs if item.get("to_role") == role
                        ],
                        "outgoing": [
                            item for item in handoffs if item.get("from_role") == role
                        ],
                    },
                }
            )

        return role_runs

    def _extract_review_decision(self, state: MultiAgentState) -> str | None:
        for artifact in state.artifacts:
            if artifact.role == "review":
                return (artifact.data or {}).get("decision")
        return None
