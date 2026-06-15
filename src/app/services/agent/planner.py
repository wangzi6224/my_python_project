from __future__ import annotations

import json
from typing import Any

from src.app.services.agent.state import AgentObservation, AgentState


# 生成稳定的工具调用 key，用于防止重复调用
def _tool_key(tool_name: str, arguments: dict[str, Any]) -> str:
    """生成稳定的工具调用 key，用于防止重复调用。"""
    return json.dumps(
        {"tool_name": tool_name, "arguments": arguments},
        ensure_ascii=False,
        sort_keys=True,
    )


# 检查工具是否已经被调用过
def _has_called(
    state: AgentState, tool_name: str, arguments: dict[str, Any] | None = None
) -> bool:
    for step in state.steps:
        if step.type != "tool_call" or step.tool_name != tool_name:
            continue
        if arguments is None or step.arguments == arguments:
            return True
    return False


# 获取最新的Observation
def _last_observation(
    state: AgentState, tool_name: str | None = None
) -> AgentObservation | None:
    for observation in reversed(state.observations):
        if tool_name is None or observation.tool_name == tool_name:
            return observation
    return None


# 提取第一个 document_id
def _extract_first_document_id(result: dict[str, Any] | None) -> str | None:
    """从 search_docs 的返回结果里尽量提取第一个 document_id。

    这里故意做成兼容型解析，避免 RagRetriever 返回结构微调时 Planner 立刻坏掉。
    """
    if not result:
        return None

    data = result.get("data")

    candidates: list[Any] = []

    if isinstance(data, dict):
        for key in ["chunks", "results", "sources", "items"]:
            value = data.get(key)
            if isinstance(value, list):
                candidates.extend(value)

        # 有些工具可能直接返回 {"document_id": "..."}
        if isinstance(data.get("document_id"), str):
            return data["document_id"]

    if isinstance(data, list):
        candidates.extend(data)

    for item in candidates:
        if not isinstance(item, dict):
            continue
        document_id = item.get("document_id") or item.get("doc_id")
        if isinstance(document_id, str) and document_id.strip():
            return document_id.strip()

    return None


class RuleBasedPlanner:
    """规则版 Agent 决策器。"""

    def plan(self, state: AgentState) -> dict[str, Any]:
        text = state.question.strip()
        search_query = (state.rewritten_question or state.question).strip()
        decision_text = f"{text}\n{search_query}"

        last_observation = _last_observation(state)
        if last_observation and not last_observation.success:
            return {
                "type": "final",
                "reason": "上一轮工具调用失败，停止继续调用工具，基于失败信息生成回答",
            }

        if any(
            keyword in decision_text
            for keyword in ["有哪些文档", "文档列表", "知识库里有什么"]
        ):
            if not _has_called(state, "list_docs"):
                return {
                    "type": "tool_call",
                    "tool_name": "list_docs",
                    "arguments": {},
                    "reason": "用户询问知识库文档列表",
                }

            return {
                "type": "final",
                "reason": "已经获取文档列表，可以生成最终回答",
            }

        need_search = any(
            keyword in decision_text
            for keyword in [
                "根据知识库",
                "根据文档",
                "规范",
                "查询",
                "检索",
                "组件模板",
            ]
        )

        need_full_doc = any(
            keyword in decision_text
            for keyword in ["详细", "完整", "分析", "生成", "模板", "总结", "对比"]
        )

        if need_search:
            search_arguments = {
                "query": search_query,
                "top_k": state.top_k,
                "score_threshold": state.score_threshold,
            }

            if not _has_called(state, "search_docs", search_arguments):
                return {
                    "type": "tool_call",
                    "tool_name": "search_docs",
                    "arguments": search_arguments,
                    "reason": "用户问题需要先检索知识库资料",
                }

            search_observation = _last_observation(state, "search_docs")
            document_id = _extract_first_document_id(
                search_observation.result if search_observation else None
            )

            if need_full_doc and document_id:
                read_arguments = {
                    "document_id": document_id,
                    "max_chars": 6000,
                }
                if not _has_called(state, "read_doc", read_arguments):
                    return {
                        "type": "tool_call",
                        "tool_name": "read_doc",
                        "arguments": read_arguments,
                        "reason": "检索结果包含相关文档，用户需要更完整上下文，继续读取文档内容",
                    }

            return {
                "type": "final",
                "reason": "已有足够工具观察结果，可以生成最终回答",
            }

        return {
            "type": "final",
            "reason": "当前问题不需要调用工具",
        }
