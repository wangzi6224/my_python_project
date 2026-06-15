from time import perf_counter
from typing import Any
from src.app.config import resolve_llm_model
from src.app.services.llm.factory import get_llm_provider


class QueryRewriter:
    def __init__(self) -> None:
        self.llm_provider = get_llm_provider()

    def rewrite(
        self,
        conversation_summary: str | None,
        recent_messages: list[dict[str, Any]],
        current_question: str,
        model: str | None = None,
        purpose: str = "rag_retrieval",
    ) -> dict[str, Any]:
        selected_model = resolve_llm_model(model=model)
        start = perf_counter()

        messages = self._build_messages(
            conversation_summary=conversation_summary,
            recent_messages=recent_messages,
            current_question=current_question,
            purpose=purpose,
        )

        try:
            response = self.llm_provider.chat(
                messages=messages,
                model=selected_model,
                thinking_enabled=False,
            )

            rewritten_query = self._clean_output(response.content)

            if not rewritten_query:
                return self._fallback(
                    current_question=current_question,
                    start=start,
                    reason="EMPTY_REWRITE_RESULT",
                )

            return {
                "original_query": current_question,
                "rewritten_query": rewritten_query,
                "rewrite_changed": rewritten_query.strip() != current_question.strip(),
                "latency_ms": int((perf_counter() - start) * 1000),
                "fallback_reason": None,
            }

        except Exception as exc:
            return self._fallback(
                current_question=current_question,
                start=start,
                reason=f"REWRITE_FAILED: {exc}",
            )

    def _build_messages(
        self,
        conversation_summary: str | None,
        recent_messages: list[dict[str, Any]],
        current_question: str,
        purpose: str = "rag_retrieval",
    ) -> list[dict[str, str]]:
        role_description = (
            "企业知识库 RAG 系统里的 Query Rewrite 模块"
            if purpose == "rag_retrieval"
            else "NexusAI Agent 的 Query Rewrite 模块"
        )
        task_description = (
            "把用户当前问题改写成一个独立、完整、适合知识库检索的问题。"
            if purpose == "rag_retrieval"
            else "把用户当前问题改写成一个独立、完整、适合工具规划和知识库检索的问题。"
        )
        system_prompt = f"""
        你是一个{role_description}。

        你的任务：
        {task_description}

        严格要求：
        1. 不要回答问题。
        2. 只输出改写后的问题。
        3. 不要输出解释。
        4. 不要输出 JSON。
        5. 不要编造用户没有表达的意图。
        6. 如果当前问题已经完整，就原样输出。
        7. 保留专有名词、代码标识符、接口路径、文件名、模型名、错误码。
        8. 使用简体中文。
        """.strip()

        user_prompt = f"""
        【会话摘要】
        {conversation_summary or "无"}

        【最近对话】
        {self._format_recent_messages(recent_messages)}

        【当前问题】
        {current_question}

        请输出改写后的检索问题：
        """.strip()

        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    def _format_recent_messages(
        self,
        recent_messages: list[dict[str, Any]],
    ) -> str:
        if not recent_messages:
            return "无"

        lines: list[str] = []

        for item in recent_messages:
            role = item.get("role", "unknown")
            content = item.get("content", "")
            lines.append(f"{role}: {content}")

        return "\n".join(lines)

    def _clean_output(self, text: str) -> str:
        cleaned = text.strip()

        if not cleaned:
            return ""

        first_line = cleaned.splitlines()[0].strip()

        for prefix in [
            "改写后的问题：",
            "改写问题：",
            "检索问题：",
            "问题：",
        ]:
            if first_line.startswith(prefix):
                first_line = first_line[len(prefix) :].strip()

        return first_line

    def _fallback(
        self,
        current_question: str,
        start: float,
        reason: str,
    ) -> dict[str, Any]:
        return {
            "original_query": current_question,
            "rewritten_query": current_question,
            "rewrite_changed": False,
            "latency_ms": int((perf_counter() - start) * 1000),
            "fallback_reason": reason,
        }
