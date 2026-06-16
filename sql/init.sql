-- =====================================================
-- 应用所需扩展
-- vector：用于保存向量嵌入和近似最近邻搜索
-- pg_trgm：用于模糊文本匹配的 trigram 索引
-- =====================================================
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- =====================================================
-- documents：上传/导入到知识库的源文件记录
-- =====================================================
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    file_type TEXT NOT NULL,
    source_path TEXT NOT NULL,
    content TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    chunk_count INTEGER NOT NULL DEFAULT 0,
    char_count INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =====================================================
-- document_chunks：文档内容的分块数据，用于检索和向量检索
-- 每条记录对应一个文档块
-- =====================================================
CREATE TABLE IF NOT EXISTS document_chunks (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    heading TEXT,
    content TEXT NOT NULL,
    char_count INTEGER NOT NULL,
    estimated_tokens INTEGER NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    embedding vector(768),
    embedding_model TEXT,
    embedding_status TEXT NOT NULL DEFAULT 'pending',
    embedding_error TEXT,
    embedding_updated_at TIMESTAMPTZ,
    -- 加权全文搜索向量：标题权重高于正文
    search_vector tsvector GENERATED ALWAYS AS (
        setweight(
            to_tsvector('simple', coalesce(heading, '')),
            'A'
        ) || setweight(to_tsvector('simple', content), 'B')
    ) STORED,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (document_id, chunk_index)
);

-- =====================================================
-- conversations：会话级元信息和摘要记录
-- =====================================================
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    summary TEXT,
    summarized_message_count INTEGER NOT NULL DEFAULT 0,
    summary_updated_at TIMESTAMPTZ,
    model TEXT NOT NULL,
    provider TEXT NOT NULL DEFAULT 'ollama',
    status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =====================================================
-- messages：会话内消息时间线记录
-- =====================================================
CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =====================================================
-- chat_history：按请求保存的问答日志，用于审计和性能分析
-- =====================================================
CREATE TABLE IF NOT EXISTS chat_history (
    id TEXT PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    model TEXT NOT NULL,
    user_input TEXT NOT NULL,
    prompt TEXT NOT NULL,
    answer TEXT NOT NULL,
    elapsed_seconds DOUBLE PRECISION NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =====================================================
-- agent_runs：每次 Agent 执行的汇总记录
-- 记录执行状态、调用次数、耗时和最终结果
-- =====================================================
CREATE TABLE IF NOT EXISTS agent_runs (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    user_message_id TEXT NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    status TEXT NOT NULL,
    input TEXT NOT NULL,
    final_answer TEXT,
    model TEXT,
    provider TEXT NOT NULL DEFAULT 'ollama',
    max_steps INTEGER NOT NULL DEFAULT 3,
    step_count INTEGER NOT NULL DEFAULT 0,
    total_latency_ms INTEGER,
    error_code TEXT,
    error_message TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =====================================================
-- agent_steps：每个 Agent 运行步骤的详细跟踪记录
-- =====================================================
CREATE TABLE IF NOT EXISTS agent_steps (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
    step_index INTEGER NOT NULL,
    step_type TEXT NOT NULL,
    thought TEXT,
    reason TEXT,
    tool_name TEXT,
    tool_arguments JSONB NOT NULL DEFAULT '{}'::jsonb,
    tool_result JSONB,
    success BOOLEAN NOT NULL DEFAULT TRUE,
    latency_ms INTEGER NOT NULL DEFAULT 0,
    error_code TEXT,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (run_id, step_index)
);

-- =====================================================
-- agent_events：Agent 运行过程中的事件记录，用于可观察性
-- =====================================================
CREATE TABLE IF NOT EXISTS agent_events (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
    step_id TEXT REFERENCES agent_steps(id) ON DELETE SET NULL,
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =====================================================
-- agent 追踪查询相关索引
-- =====================================================
CREATE INDEX IF NOT EXISTS idx_agent_runs_conversation_id_created_at
ON agent_runs (conversation_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_agent_steps_run_id_step_index
ON agent_steps (run_id, step_index ASC);

CREATE INDEX IF NOT EXISTS idx_agent_events_run_id_created_at
ON agent_events (run_id, created_at ASC);


-- =====================================================
-- assistant_runs：每次 Assistant 调用的汇总记录
-- 记录调用状态、输入输出、耗时和调用细节
-- =====================================================
CREATE TABLE IF NOT EXISTS assistant_runs (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    user_message_id TEXT,
    assistant_message_id TEXT,
    mode TEXT NOT NULL,
    status TEXT NOT NULL,
    input TEXT NOT NULL,
    final_answer TEXT,
    model TEXT,
    provider TEXT,
    latency_ms INTEGER,
    trace JSONB NOT NULL DEFAULT '{}'::jsonb,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =====================================================
-- 文档检索、向量搜索与会话时间线索引
-- =====================================================
CREATE INDEX IF NOT EXISTS idx_documents_updated_at ON documents (updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_document_chunks_document_id ON document_chunks (document_id);
CREATE INDEX IF NOT EXISTS idx_document_chunks_embedding_status ON document_chunks (embedding_status);
-- HNSW ANN 索引用于 embedding 向量的余弦相似度搜索
CREATE INDEX IF NOT EXISTS idx_document_chunks_embedding_hnsw ON document_chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_conversations_updated_at ON conversations (updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_messages_conversation_id_created_at ON messages (conversation_id, created_at ASC);
CREATE INDEX IF NOT EXISTS idx_chat_history_created_at ON chat_history (created_at ASC);
-- 用于检索流程的全文和模糊文本索引
CREATE INDEX IF NOT EXISTS idx_document_chunks_search_vector ON document_chunks USING GIN (search_vector);
CREATE INDEX IF NOT EXISTS idx_document_chunks_content_trgm ON document_chunks USING GIN (content gin_trgm_ops);
-- Agent 追踪相关索引
CREATE INDEX IF NOT EXISTS idx_assistant_runs_conversation_id
ON assistant_runs(conversation_id);
-- 按创建时间倒序索引，优化最近调用的查询性能
CREATE INDEX IF NOT EXISTS idx_assistant_runs_created_at
ON assistant_runs(created_at DESC);
-- 状态索引，便于统计不同状态的调用数量和性能分析
CREATE INDEX IF NOT EXISTS idx_assistant_runs_status
ON assistant_runs(status);

-- =====================================================
-- conversation_states：当前会话的结构化短期记忆
-- 一条 conversation 对应一条 state
-- =====================================================
CREATE TABLE IF NOT EXISTS conversation_states (
    conversation_id TEXT PRIMARY KEY REFERENCES conversations(id) ON DELETE CASCADE,

    current_goal TEXT,
    current_topic TEXT,

    confirmed_facts JSONB NOT NULL DEFAULT '[]'::jsonb,
    confirmed_constraints JSONB NOT NULL DEFAULT '[]'::jsonb,
    user_preferences JSONB NOT NULL DEFAULT '[]'::jsonb,
    open_questions JSONB NOT NULL DEFAULT '[]'::jsonb,

    task_state JSONB NOT NULL DEFAULT '{}'::jsonb,

    source TEXT NOT NULL DEFAULT 'assistant_auto_extract',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_conversation_states_updated_at
ON conversation_states(updated_at DESC);

-- =====================================================
-- memory_items：跨会话长期记忆
-- =====================================================
CREATE TABLE IF NOT EXISTS memory_items (
    id TEXT PRIMARY KEY,

    user_id TEXT NOT NULL DEFAULT 'default_user',
    workspace_id TEXT,

    conversation_id TEXT REFERENCES conversations(id) ON DELETE SET NULL,
    source_message_id TEXT REFERENCES messages(id) ON DELETE SET NULL,
    source_run_id TEXT,

    memory_type TEXT NOT NULL,

    content TEXT NOT NULL,
    normalized_content TEXT,

    embedding vector(768),
    embedding_model TEXT,
    embedding_status TEXT NOT NULL DEFAULT 'pending',
    embedding_error TEXT,
    embedding_updated_at TIMESTAMPTZ,

    importance NUMERIC NOT NULL DEFAULT 0.5 CHECK (importance >= 0 AND importance <= 1),
    confidence NUMERIC NOT NULL DEFAULT 0.5 CHECK (confidence >= 0 AND confidence <= 1),

    access_count INTEGER NOT NULL DEFAULT 0,
    last_accessed_at TIMESTAMPTZ,

    expires_at TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'active',

    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT memory_items_type_check CHECK (
        memory_type IN (
            'user_profile',
            'semantic',
            'episodic',
            'tool_preference',
            'project'
        )
    ),

    CONSTRAINT memory_items_status_check CHECK (
        status IN ('active', 'archived', 'deleted')
    )
);

CREATE INDEX IF NOT EXISTS idx_memory_items_user_type_status
ON memory_items(user_id, memory_type, status);

CREATE INDEX IF NOT EXISTS idx_memory_items_workspace
ON memory_items(workspace_id);

CREATE INDEX IF NOT EXISTS idx_memory_items_conversation_id
ON memory_items(conversation_id);

CREATE INDEX IF NOT EXISTS idx_memory_items_source_message_id
ON memory_items(source_message_id);

CREATE INDEX IF NOT EXISTS idx_memory_items_embedding_hnsw
ON memory_items USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS idx_memory_items_normalized_content_trgm
ON memory_items USING GIN (normalized_content gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_memory_items_updated_at
ON memory_items(updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_memory_items_importance
ON memory_items(importance DESC);


CREATE TABLE IF NOT EXISTS mcp_tool_audit_logs (
    id TEXT PRIMARY KEY,
    assistant_run_id TEXT,
    agent_run_id TEXT,
    conversation_id TEXT,
    server_name TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    full_tool_name TEXT NOT NULL,
    arguments JSONB NOT NULL DEFAULT '{}'::jsonb,
    success BOOLEAN NOT NULL,
    error_code TEXT,
    error_message TEXT,
    latency_ms INTEGER,
    result_chars INTEGER NOT NULL DEFAULT 0,
    risk_level TEXT NOT NULL DEFAULT 'low',
    source TEXT NOT NULL DEFAULT 'mcp',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_mcp_tool_audit_logs_conversation
ON mcp_tool_audit_logs(conversation_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_mcp_tool_audit_logs_agent_run
ON mcp_tool_audit_logs(agent_run_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_mcp_tool_audit_logs_tool
ON mcp_tool_audit_logs(server_name, tool_name, created_at DESC);

-- =====================================================
-- mcp_servers：第三方 MCP Server 动态注册配置
-- =====================================================
CREATE TABLE IF NOT EXISTS mcp_servers (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    transport TEXT NOT NULL DEFAULT 'stdio',
    command TEXT NOT NULL,
    args JSONB NOT NULL DEFAULT '[]'::jsonb,
    env JSONB NOT NULL DEFAULT '{}'::jsonb,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    timeout_seconds INTEGER NOT NULL DEFAULT 15,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT mcp_servers_transport_check CHECK (
        transport IN ('stdio')
    ),

    CONSTRAINT mcp_servers_timeout_check CHECK (
        timeout_seconds >= 1 AND timeout_seconds <= 120
    )
);

CREATE INDEX IF NOT EXISTS idx_mcp_servers_enabled
ON mcp_servers(enabled);

-- =====================================================
-- mcp_tools：第三方 MCP Tool 动态注册配置
-- =====================================================
CREATE TABLE IF NOT EXISTS mcp_tools (
    id TEXT PRIMARY KEY,
    server_id TEXT NOT NULL REFERENCES mcp_servers(id) ON DELETE CASCADE,
    server_name TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    full_name TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL DEFAULT '',
    input_schema JSONB NOT NULL DEFAULT '{}'::jsonb,
    risk_level TEXT NOT NULL DEFAULT 'low',
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    discovered_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT mcp_tools_risk_level_check CHECK (
        risk_level IN ('low', 'medium', 'high')
    ),

    UNIQUE (server_id, tool_name)
);

CREATE INDEX IF NOT EXISTS idx_mcp_tools_server_enabled
ON mcp_tools(server_id, enabled);

CREATE INDEX IF NOT EXISTS idx_mcp_tools_full_name
ON mcp_tools(full_name);

-- =====================================================
-- trace_spans：LLMOps 统一链路追踪 Span
-- =====================================================
CREATE TABLE IF NOT EXISTS trace_spans (
    id TEXT PRIMARY KEY,
    trace_id TEXT NOT NULL,
    parent_span_id TEXT,
    run_id TEXT NOT NULL,
    conversation_id TEXT,
    assistant_run_id TEXT,
    agent_run_id TEXT,

    span_type TEXT NOT NULL,
    name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'running',

    input JSONB,
    output JSONB,
    error_code TEXT,
    error_message TEXT,

    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,

    latency_ms INTEGER,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at TIMESTAMPTZ,

    CONSTRAINT trace_spans_status_check CHECK (
        status IN ('running', 'success', 'error', 'cancelled')
    )
);

CREATE INDEX IF NOT EXISTS idx_trace_spans_trace_id_started_at
ON trace_spans(trace_id, started_at ASC);

CREATE INDEX IF NOT EXISTS idx_trace_spans_parent
ON trace_spans(parent_span_id);

CREATE INDEX IF NOT EXISTS idx_trace_spans_run_id
ON trace_spans(run_id);

CREATE INDEX IF NOT EXISTS idx_trace_spans_assistant_run
ON trace_spans(assistant_run_id);

CREATE INDEX IF NOT EXISTS idx_trace_spans_agent_run
ON trace_spans(agent_run_id);

CREATE INDEX IF NOT EXISTS idx_trace_spans_type
ON trace_spans(span_type);

CREATE INDEX IF NOT EXISTS idx_trace_spans_status
ON trace_spans(status);


CREATE TABLE IF NOT EXISTS multi_agent_runs (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    assistant_run_id TEXT,
    user_message_id TEXT,
    assistant_message_id TEXT,
    status TEXT NOT NULL,
    input TEXT NOT NULL,
    final_answer TEXT,
    supervisor_plan JSONB NOT NULL DEFAULT '{}'::jsonb,
    enabled_roles JSONB NOT NULL DEFAULT '[]'::jsonb,
    finish_reason TEXT,
    model TEXT,
    provider TEXT,
    latency_ms INTEGER,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_multi_agent_runs_conversation
ON multi_agent_runs(conversation_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_multi_agent_runs_assistant_run
ON multi_agent_runs(assistant_run_id);

CREATE TABLE IF NOT EXISTS multi_agent_role_runs (
    id TEXT PRIMARY KEY,
    multi_agent_run_id TEXT NOT NULL REFERENCES multi_agent_runs(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    status TEXT NOT NULL,
    input JSONB NOT NULL DEFAULT '{}'::jsonb,
    output JSONB,
    artifact_id TEXT,
    error_code TEXT,
    error_message TEXT,
    latency_ms INTEGER,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_multi_agent_role_runs_run
ON multi_agent_role_runs(multi_agent_run_id, created_at);

CREATE INDEX IF NOT EXISTS idx_multi_agent_role_runs_role
ON multi_agent_role_runs(role, created_at DESC);

CREATE TABLE IF NOT EXISTS multi_agent_handoffs (
    id TEXT PRIMARY KEY,
    multi_agent_run_id TEXT NOT NULL REFERENCES multi_agent_runs(id) ON DELETE CASCADE,
    from_role TEXT NOT NULL,
    to_role TEXT NOT NULL,
    task_id TEXT,
    summary TEXT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    confidence NUMERIC NOT NULL DEFAULT 0.5,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_multi_agent_handoffs_run
ON multi_agent_handoffs(multi_agent_run_id, created_at);

CREATE TABLE IF NOT EXISTS multi_agent_artifacts (
    id TEXT PRIMARY KEY,
    multi_agent_run_id TEXT NOT NULL REFERENCES multi_agent_runs(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    artifact_type TEXT NOT NULL,
    title TEXT,
    content TEXT NOT NULL,
    data JSONB NOT NULL DEFAULT '{}'::jsonb,
    source_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
    confidence NUMERIC NOT NULL DEFAULT 0.5,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_multi_agent_artifacts_run
ON multi_agent_artifacts(multi_agent_run_id, created_at);

CREATE INDEX IF NOT EXISTS idx_multi_agent_artifacts_role
ON multi_agent_artifacts(role, created_at DESC);
