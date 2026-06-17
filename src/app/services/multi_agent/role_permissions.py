from src.app.services.multi_agent.schemas import AgentRole


ROLE_ALLOWED_TOOLS: dict[AgentRole, list[str]] = {
    "supervisor": [],
    "research": [
        "list_docs",
        "search_docs",
        "read_doc",
    ],
    "coding": [
        "search_docs",
        "read_doc",
    ],
    "review": [
        "search_docs",
        "read_doc",
    ],
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
    mcp_allowed_tools: list[str] | None = None,
) -> list[str]:
    allowed = list(ROLE_ALLOWED_TOOLS.get(role, []))

    if not enable_mcp_tools:
        return allowed

    prefixes = ROLE_ALLOWED_MCP_PREFIXES.get(role, [])
    for tool_name in mcp_allowed_tools or []:
        if any(tool_name.startswith(prefix) for prefix in prefixes):
            allowed.append(tool_name)

    return allowed
