from __future__ import annotations

from src.app.config import get_mcp_allowed_tools
from src.app.services.mcp.registry import McpRegistry
from src.app.services.multi_agent.role_permissions import get_role_allowed_tools
from src.app.services.multi_agent.schemas import AgentRole
from src.app.services.tools.list_docs import ListDocsTool
from src.app.services.tools.read_doc import ReadDocTool
from src.app.services.tools.registry import ToolRegistry
from src.app.services.tools.search_docs import SearchDocsTool


class RoleToolRegistryFactory:
    def build(
        self,
        *,
        role: AgentRole,
        enable_mcp_tools: bool,
    ) -> ToolRegistry:
        allowed_tools = get_role_allowed_tools(
            role,
            enable_mcp_tools=enable_mcp_tools,
            mcp_allowed_tools=get_mcp_allowed_tools(),
        )

        registry = ToolRegistry(allowed_tools=allowed_tools)

        for tool in (ListDocsTool(), SearchDocsTool(), ReadDocTool()):
            registry.register(tool)

        if enable_mcp_tools:
            McpRegistry().register_to_tool_registry(registry)

        return registry
