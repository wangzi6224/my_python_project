from __future__ import annotations

from src.app.services.multi_agent.schemas import AgentRole

ROLE_ALLOWED_TOOLS: dict[AgentRole, list[str]] = {
    "supervisor": [],
    "research": [
        "list_docs",
        "search_docs",
        "read_doc",
        # TODO 还没开始做
        # "search_graph",
        # "inspect_entity_graph",
    ],
    "coding": [],
    "review": [],
    "final_synthesizer": [],
}


ROLE_ALLOWED_MCP_PREFIXES: dict[AgentRole, list[str]] = {
    "supervisor": [],
    "research": ["mcp__"],
    "coding": [],
    "review": [],
    "final_synthesizer": [],
}


def get_role_allowed_tools(
    role: AgentRole,
    *,
    enable_mcp_tools: bool,
    mcp_allowed_tools: list[str],
) -> list[str]:
    tools = list(ROLE_ALLOWED_TOOLS.get(role, []))

    if enable_mcp_tools:
        prefixes = ROLE_ALLOWED_MCP_PREFIXES.get(role, [])
        for tool in mcp_allowed_tools:
            if any(tool.startswith(prefix) for prefix in prefixes):
                tools.append(tool)

    return tools
