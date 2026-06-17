from __future__ import annotations

from time import perf_counter
from typing import Any
from uuid import uuid4

from src.app.config import get_mcp_allowed_tools
from src.app.services.mcp.registry import McpRegistry
from src.app.services.multi_agent.agents.autonomous_role_agent import AutonomousRoleAgent
from src.app.services.multi_agent.prompts import RESEARCH_PROMPT_VERSION
from src.app.services.multi_agent.role_permissions import get_role_allowed_tools
from src.app.services.multi_agent.schemas import AgentArtifact, RoleRunResult, SourceRef
from src.app.services.tools.list_docs import ListDocsTool
from src.app.services.tools.read_doc import ReadDocTool
from src.app.services.tools.registry import ToolRegistry
from src.app.services.tools.search_docs import SearchDocsTool


class ResearchAgent(AutonomousRoleAgent):
    role = "research"
    prompt_version = RESEARCH_PROMPT_VERSION
    artifact_type = "research_report"
    default_artifact_title = "ResearchAgent 研究报告"

    def run(
        self,
        *,
        question: str,
        top_k: int,
        score_threshold: float,
        enable_mcp_tools: bool,
        model: str | None = None,
        **_: Any,
    ) -> RoleRunResult:
        start = perf_counter()
        registry = self._build_research_tool_registry(
            enable_mcp_tools=enable_mcp_tools,
        )

        tool_calls: list[dict[str, Any]] = []
        source_refs: list[SourceRef] = []
        confirmed_facts: list[str] = []
        open_questions: list[str] = []

        search_args = {
            "query": question,
            "top_k": top_k,
            "score_threshold": score_threshold,
        }

        search_result = self._call_tool(
            registry=registry,
            tool_name="search_docs",
            arguments=search_args,
        )
        tool_calls.append(search_result)

        if not search_result.get("success"):
            open_questions.append("search_docs 执行失败，无法确认项目资料。")
        else:
            data = search_result.get("result", {}).get("data") or {}
            items = data.get("items") or data.get("chunks") or data.get("sources") or []
            for item in items[:top_k]:
                if not isinstance(item, dict):
                    continue
                source_refs.append(
                    SourceRef(
                        type="chunk",
                        id=item.get("chunk_id") or item.get("id"),
                        title=item.get("filename") or item.get("heading"),
                        score=item.get("score")
                        or item.get("rrf_score")
                        or item.get("rerank_score"),
                        metadata={
                            "document_id": item.get("document_id"),
                            "heading": item.get("heading"),
                        },
                    )
                )
                preview = item.get("content") or item.get("content_preview") or ""
                if preview:
                    confirmed_facts.append(preview[:500])

        content = self._build_research_content(
            question=question,
            confirmed_facts=confirmed_facts,
            open_questions=open_questions,
            source_refs=source_refs,
        )

        artifact = AgentArtifact(
            id=f"artifact_{uuid4().hex}",
            role="research",
            artifact_type="research_report",
            title="ResearchAgent 研究报告",
            content=content,
            data={
                "confirmed_facts": confirmed_facts,
                "open_questions": open_questions,
                "tool_call_count": len(tool_calls),
            },
            source_refs=source_refs,
            confidence=0.75 if confirmed_facts else 0.35,
            metadata={
                "prompt_version": self.prompt_version,
                "latency_ms": int((perf_counter() - start) * 1000),
            },
        )

        return RoleRunResult(
            role="research",
            status="completed",
            artifact=artifact,
            latency_ms=int((perf_counter() - start) * 1000),
            trace={
                "tool_calls": tool_calls,
                "source_count": len(source_refs),
                "confirmed_fact_count": len(confirmed_facts),
            },
        )

    def _build_research_tool_registry(self, *, enable_mcp_tools: bool) -> ToolRegistry:
        allowed_tools = get_role_allowed_tools(
            "research",
            enable_mcp_tools=enable_mcp_tools,
            mcp_allowed_tools=get_mcp_allowed_tools(),
        )
        registry = ToolRegistry(allowed_tools=allowed_tools)

        for tool in (ListDocsTool(), SearchDocsTool(), ReadDocTool()):
            registry.register(tool)

        if enable_mcp_tools:
            McpRegistry().register_to_tool_registry(registry)

        return registry

    def _call_tool(
        self,
        *,
        registry: ToolRegistry,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        start = perf_counter()
        try:
            registry.validate_arguments(tool_name, arguments)
            tool = registry.get(tool_name)
            result = tool.run(arguments)
            source = getattr(tool, "source", "internal")
            return {
                "tool_name": tool_name,
                "arguments": arguments,
                "success": bool(result.get("success")),
                "latency_ms": int((perf_counter() - start) * 1000),
                "source": source,
                "role": self.role,
                "metadata": {
                    "source": source,
                    "role": self.role,
                },
                "result": result,
            }
        except Exception as exc:
            return {
                "tool_name": tool_name,
                "arguments": arguments,
                "success": False,
                "latency_ms": int((perf_counter() - start) * 1000),
                "source": "internal",
                "role": self.role,
                "metadata": {
                    "source": "internal",
                    "role": self.role,
                },
                "error_code": exc.__class__.__name__,
                "error_message": str(exc),
            }

    def _build_research_content(
        self,
        *,
        question: str,
        confirmed_facts: list[str],
        open_questions: list[str],
        source_refs: list[SourceRef],
    ) -> str:
        return "\n".join(
            [
                "ResearchAgent 研究报告",
                "",
                f"用户问题：{question}",
                "",
                "已确认事实：",
                "\n".join(f"- {fact}" for fact in confirmed_facts[:10]) or "- 暂无",
                "",
                "未确认问题：",
                "\n".join(f"- {item}" for item in open_questions) or "- 暂无",
                "",
                "来源：",
                "\n".join(
                    f"- {src.title or src.id} score={src.score}"
                    for src in source_refs[:10]
                )
                or "- 暂无",
            ]
        )
