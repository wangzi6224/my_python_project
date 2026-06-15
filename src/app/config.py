from functools import lru_cache
import os
from typing import Any, Final

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


# Settings 类用于统一管理应用配置，按功能类别分组，支持从 .env 或环境变量加载。
class Settings(BaseSettings):
    # 应用级配置：运行环境、日志级别、聊天记录存储路径
    app_env: str = Field(default="development", alias="APP_ENV")
    app_log_level: str = Field(default="INFO", alias="APP_LOG_LEVEL")
    # 工具结果默认最大字符数，避免过长导致上下文超限或性能问题
    tool_max_chars_default: Final = 40000
    chat_history_path: str = Field(
        default="chat_history.json",
        alias="CHAT_HISTORY_PATH",
    )

    nexusai_mcp_token: str = Field(default="", alias="NEXUSAI_MCP_TOKEN")
    nexusai_mcp_max_result_chars: int = Field(
        default=tool_max_chars_default, alias="NEXUSAI_MCP_MAX_RESULT_CHARS"
    )

    # Ollama 相关配置：LLM 服务地址、模型与请求行为
    ollama_base_url: str = Field(
        default="http://localhost:11434",
        alias="OLLAMA_BASE_URL",
    )
    ollama_model: str = Field(
        default="gemma4:e2b",
        alias="OLLAMA_MODEL",
    )
    ollama_timeout: int = Field(
        default=1200,
        alias="OLLAMA_TIMEOUT",
    )
    ollama_keep_alive: str = Field(
        default="5m",
        alias="OLLAMA_KEEP_ALIVE",
    )

    # LLM Provider 选择：顶层只区分本地 Ollama 与云端 OpenAI 兼容服务
    llm_provider: str = Field(default="ollama", alias="LLM_PROVIDER")
    cloud_provider: str = Field(default="deepseek", alias="CLOUD_PROVIDER")

    # DeepSeek 线上 API 配置，兼容 OpenAI Chat Completions 接口
    deepseek_base_url: str = Field(
        default="https://api.deepseek.com",
        alias="DEEPSEEK_BASE_URL",
    )
    deepseek_api_key: str = Field(
        default=os.getenv("ANTHROPIC_AUTH_TOKEN", ""),
        validation_alias=AliasChoices("DEEPSEEK_API_KEY", "ANTHROPIC_AUTH_TOKEN"),
    )
    deepseek_model: str = Field(
        default="deepseek-v4-flash",
        alias="DEEPSEEK_MODEL",
    )
    deepseek_timeout: int = Field(default=120, alias="DEEPSEEK_TIMEOUT")
    qwen_base_url: str = Field(
        default="https://dashscope.aliyuncs.com/compatible-mode/v1",
        alias="QWEN_BASE_URL",
    )
    qwen_api_key: str = Field(
        default=os.getenv("QWEN_API_KEY", ""),
    )
    qwen_model: str = Field(default="qwen3.7-max", alias="QWEN_MODEL")
    qwen_timeout: int = Field(default=120, alias="QWEN_TIMEOUT")
    glm_base_url: str = Field(
        default="https://open.bigmodel.cn/api/paas/v4",
        validation_alias=AliasChoices("GLM_BASE_URL", "GML_BASE_URL"),
    )
    glm_api_key: str = Field(default=os.getenv("GLM_API_KEY", ""))
    glm_model: str = Field(
        default="glm-5.1",
        validation_alias=AliasChoices("GLM_MODEL"),
    )
    glm_timeout: int = Field(
        default=120,
        validation_alias=AliasChoices("GLM_TIMEOUT", "GML_TIMEOUT"),
    )

    # PostgreSQL 数据库配置
    postgres_host: str = Field(default="localhost", alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, alias="POSTGRES_PORT")
    postgres_db: str = Field(default="ai_backend", alias="POSTGRES_DB")
    postgres_user: str = Field(default="wangzilong", alias="POSTGRES_USER")
    postgres_password: str = Field(
        default="ai_backend_password",
        alias="POSTGRES_PASSWORD",
    )

    # Embedding 相关配置
    embedding_model: str = Field(
        default="intfloat/multilingual-e5-base",
        alias="EMBEDDING_MODEL",
    )
    embedding_batch_size: int = Field(default=1500, alias="EMBEDDING_BATCH_SIZE")
    embedding_dimension: int = Field(default=768, alias="EMBEDDING_DIMENSION")

    # Reranker / RAG 相关配置
    reranker_enabled: bool = Field(default=True, alias="RERANKER_ENABLED")
    reranker_model: str = Field(
        default="BAAI/bge-reranker-base",
        alias="RERANKER_MODEL",
    )
    reranker_use_fp16: bool = Field(default=False, alias="RERANKER_USE_FP16")

    rag_candidate_k: int = Field(default=30, alias="RAG_CANDIDATE_K")
    rag_rerank_top_n: int = Field(default=5, alias="RAG_RERANK_TOP_N")
    rag_max_rerank_content_chars: int = Field(
        default=1200,
        alias="RAG_MAX_RERANK_CONTENT_CHARS",
    )

    rag_default_retrieval_mode: str = Field(
        default="vector_rerank",
        alias="RAG_DEFAULT_RETRIEVAL_MODE",
    )
    rag_vector_top_k: int = Field(default=30, alias="RAG_VECTOR_TOP_K")
    rag_keyword_top_k: int = Field(default=30, alias="RAG_KEYWORD_TOP_K")
    rag_fusion_top_k: int = Field(default=20, alias="RAG_FUSION_TOP_K")
    rag_rrf_k: int = Field(default=60, alias="RAG_RRF_K")
    rag_mmr_enabled: bool = Field(default=True, alias="RAG_MMR_ENABLED")
    rag_mmr_lambda: float = Field(default=0.7, alias="RAG_MMR_LAMBDA")

    # Assistant / Agent 步骤上限
    agent_max_steps: int = Field(default=15, ge=1, le=20, alias="AGENT_MAX_STEPS")

    agent_planner_type: str = Field(default="llm", alias="AGENT_PLANNER_TYPE")
    agent_planner_temperature: float = Field(
        default=0.0, alias="AGENT_PLANNER_TEMPERATURE"
    )
    agent_planner_timeout_seconds: int = Field(
        default=8, alias="AGENT_PLANNER_TIMEOUT_SECONDS"
    )
    agent_query_rewrite_enabled: bool = Field(
        default=True, alias="AGENT_QUERY_REWRITE_ENABLED"
    )
    agent_query_rewrite_min_history: int = Field(
        default=2, ge=0, alias="AGENT_QUERY_REWRITE_MIN_HISTORY"
    )
    agent_query_rewrite_short_query_chars: int = Field(
        default=12, ge=1, alias="AGENT_QUERY_REWRITE_SHORT_QUERY_CHARS"
    )

    llm_router_model: str = Field(
        default="deepseek-v4-flash",
        alias="LLM_ROUTER_MODEL",
    )

    max_context_default_tokens: int = Field(
        default=1048576, alias="MAX_CONTEXT_TOKENS_DEFAULT"
    )
    llm_max_context_tokens: str = Field(
        default=(
            "glm-5.1:198000,"
            "deepseek-v4-flash:1048576,"
            "deepseek-v4-pro:1048576,"
            "qwen3.7-max:1048576"
        ),
        alias="LLM_MAX_CONTEXT_TOKENS",
    )

    # Agent 工具调用相关配置
    agent_allowed_tools: str = Field(
        default="list_docs,search_docs,read_doc",
        alias="AGENT_ALLOWED_TOOLS",
    )
    agent_tool_timeout_seconds: int = Field(
        default=10,
        alias="AGENT_TOOL_TIMEOUT_SECONDS",
    )
    agent_max_tool_result_chars: int = Field(
        default=tool_max_chars_default,
        alias="AGENT_MAX_TOOL_RESULT_CHARS",
    )

    langfuse_enabled: bool = Field(default=False, alias="LANGFUSE_ENABLED")
    langfuse_public_key: str = Field(default="", alias="LANGFUSE_PUBLIC_KEY")
    langfuse_secret_key: str = Field(default="", alias="LANGFUSE_SECRET_KEY")
    langfuse_host: str = Field(default="", alias="LANGFUSE_HOST")

    otel_enabled: bool = Field(default=False, alias="OTEL_ENABLED")
    otel_exporter_otlp_endpoint: str = Field(
        default="", alias="OTEL_EXPORTER_OTLP_ENDPOINT"
    )

    observability_enabled: bool = Field(default=True, alias="OBSERVABILITY_ENABLED")
    trace_input_max_chars: int = Field(default=2000, alias="TRACE_INPUT_MAX_CHARS")
    trace_output_max_chars: int = Field(default=3000, alias="TRACE_OUTPUT_MAX_CHARS")
    trace_store_full_prompt: bool = Field(
        default=False, alias="TRACE_STORE_FULL_PROMPT"
    )

    mcp_enabled: bool = Field(default=False, alias="MCP_ENABLED")
    mcp_allowed_tools: str = Field(default="", alias="MCP_ALLOWED_TOOLS")
    mcp_max_result_chars: int = Field(
        default=tool_max_chars_default, alias="MCP_MAX_RESULT_CHARS"
    )
    mcp_default_timeout_seconds: int = Field(
        default=15, alias="MCP_DEFAULT_TIMEOUT_SECONDS"
    )

    model_config = SettingsConfigDict(
        env_file=[".env", ".env.api_keys"],
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """获取全局 Settings 实例并缓存，避免重复读取环境变量。"""
    return Settings()


# Ollama / LLM 相关函数
def get_ollama_base_url() -> str:
    """返回 Ollama API 基础 URL，去除末尾斜杠。"""
    return get_settings().ollama_base_url.rstrip("/")


def get_ollama_model() -> str:
    """返回当前使用的 Ollama 模型名称。"""
    return get_settings().ollama_model


def get_ollama_timeout() -> int:
    """返回 Ollama 请求超时时间（秒）。"""
    return get_settings().ollama_timeout


def get_ollama_keep_alive() -> str:
    """返回 Ollama keep-alive 配置。"""
    return get_settings().ollama_keep_alive


def get_supported_llm_providers() -> list[str]:
    """返回当前代码支持的 LLM Provider 列表。"""
    return ["ollama", "cloud"]


def get_supported_cloud_providers() -> list[str]:
    """返回云端 OpenAI 兼容模型供应商列表。"""
    return ["deepseek", "qwen", "glm"]


def normalize_llm_provider(provider: str | None) -> str:
    """归一化顶层 Provider 名称，并兼容旧的 deepseek 选项。"""
    provider_name = (provider or "ollama").lower().strip()
    if provider_name in {"deepseek", "qwen", "gml", "glm"}:
        return "cloud"
    return provider_name


def normalize_cloud_provider(cloud_provider: str | None) -> str:
    """归一化云端模型供应商名称。"""
    provider_name = (cloud_provider or "deepseek").lower().strip()
    if provider_name == "gml":
        return "glm"
    return provider_name


def get_llm_provider_name() -> str:
    """返回当前 LLM Provider 名称。"""
    try:
        from src.app.runtime_config import get_selected_provider

        return get_selected_provider()
    except Exception:
        return normalize_llm_provider(get_settings().llm_provider)


def get_cloud_provider_name() -> str:
    """返回当前 Cloud 下选中的供应商名称。"""
    try:
        from src.app.runtime_config import get_selected_cloud_provider

        return get_selected_cloud_provider()
    except Exception:
        return normalize_cloud_provider(get_settings().cloud_provider)


def get_default_llm_model(
    provider: str | None = None,
    cloud_provider: str | None = None,
) -> str:
    """返回当前 Provider 对应的默认模型名称。"""
    settings = get_settings()
    provider_name = normalize_llm_provider(provider or settings.llm_provider)

    if provider_name == "cloud":
        cloud_provider_name = normalize_cloud_provider(
            cloud_provider or settings.cloud_provider
        )
        if cloud_provider_name == "qwen":
            return settings.qwen_model
        if cloud_provider_name == "glm":
            return settings.glm_model
        return settings.deepseek_model

    return settings.ollama_model


def get_cloud_provider_config(cloud_provider: str | None = None) -> dict[str, Any]:
    """返回指定云端供应商的 OpenAI SDK 连接配置。"""
    settings = get_settings()
    provider_name = normalize_cloud_provider(
        cloud_provider or get_cloud_provider_name()
    )

    if provider_name == "qwen":
        return {
            "cloud_provider": "qwen",
            "display_name": "Qwen",
            "base_url": settings.qwen_base_url.rstrip("/"),
            "api_key": settings.qwen_api_key,
            "api_key_env": "QWEN_API_KEY",
            "model": settings.qwen_model,
            "timeout": settings.qwen_timeout,
        }

    if provider_name == "glm":
        return {
            "cloud_provider": "glm",
            "display_name": "GLM",
            "base_url": settings.glm_base_url.rstrip("/"),
            "api_key": settings.glm_api_key,
            "api_key_env": "GLM_API_KEY",
            "model": settings.glm_model,
            "timeout": settings.glm_timeout,
        }

    return {
        "cloud_provider": "deepseek",
        "display_name": "DeepSeek",
        "base_url": settings.deepseek_base_url.rstrip("/"),
        "api_key": settings.deepseek_api_key,
        "api_key_env": "DEEPSEEK_API_KEY",
        "model": settings.deepseek_model,
        "timeout": settings.deepseek_timeout,
    }


def _normalize_model_key(model: str | None) -> str:
    return (model or "").strip().lower()


def get_llm_max_context_token_map() -> dict[str, int]:
    """返回按模型配置的最大上下文 token 数。

    配置格式：
    LLM_MAX_CONTEXT_TOKENS=glm-5.1:198000,deepseek-v4-flash:1048576
    """
    settings = get_settings()
    result: dict[str, int] = {}

    for item in settings.llm_max_context_tokens.split(","):
        if ":" not in item:
            continue

        model, raw_tokens = item.split(":", 1)
        model_key = _normalize_model_key(model)
        if not model_key:
            continue

        try:
            tokens = int(raw_tokens.strip())
        except ValueError:
            continue

        if tokens > 0:
            result[model_key] = tokens

    return result


def get_max_context_tokens_limit(model: str | None) -> int:
    """按模型名称返回上下文窗口上限，未知模型回落到默认配置。"""
    default_tokens = get_context_context_token_by_config()
    model_key = _normalize_model_key(model)

    if not model_key:
        return default_tokens

    return get_llm_max_context_token_map().get(model_key, default_tokens)


def resolve_max_context_tokens(
    model: str | None,
    requested_tokens: int | None = None,
) -> int:
    """解析一次请求实际使用的上下文 token 上限。

    模型配置是硬上限；请求参数只允许在该上限内进一步收紧。
    """
    model_limit = get_max_context_tokens_limit(model)

    if requested_tokens is None:
        return model_limit

    return min(requested_tokens, model_limit)


def get_cloud_provider_name_for_model(model: str | None) -> str | None:
    """按模型名称推断云端供应商，无法判断时返回 None。"""
    if not model:
        return None

    model_name = model.lower().strip()
    if model_name.startswith("deepseek"):
        return "deepseek"
    if model_name.startswith("qwen"):
        return "qwen"
    if model_name.startswith("glm"):
        return "glm"

    settings = get_settings()
    configured_models = {
        settings.deepseek_model.lower().strip(): "deepseek",
        settings.qwen_model.lower().strip(): "qwen",
        settings.glm_model.lower().strip(): "glm",
    }
    return configured_models.get(model_name)


def resolve_llm_model(
    model: str | None = None,
    stored_model: str | None = None,
    stored_provider: str | None = None,
    provider: str | None = None,
) -> str:
    """按当前 Provider 解析本次请求应使用的模型。"""
    if model:
        return model

    current_provider = normalize_llm_provider(provider or get_llm_provider_name())
    if stored_model and (not stored_provider or stored_provider == current_provider):
        return stored_model

    try:
        from src.app.runtime_config import get_selected_model

        return get_selected_model(current_provider)
    except Exception:
        return get_default_llm_model(current_provider)


# 应用级配置函数
def get_log_level() -> str:
    """返回当前日志级别。"""
    return get_settings().app_log_level


def get_chat_history_path() -> str:
    """返回聊天历史记录文件存储路径。"""
    return get_settings().chat_history_path


# Embedding 相关配置函数
def get_embedding_model() -> str:
    return get_settings().embedding_model


def get_embedding_batch_size() -> int:
    return get_settings().embedding_batch_size


def get_embedding_dimension() -> int:
    return get_settings().embedding_dimension


# Reranker / RAG 相关配置函数
def is_reranker_enabled() -> bool:
    return get_settings().reranker_enabled


def get_reranker_model() -> str:
    return get_settings().reranker_model


def get_reranker_use_fp16() -> bool:
    return get_settings().reranker_use_fp16


def get_rag_candidate_k() -> int:
    return get_settings().rag_candidate_k


def get_rag_rerank_top_n() -> int:
    return get_settings().rag_rerank_top_n


def get_rag_max_rerank_content_chars() -> int:
    return get_settings().rag_max_rerank_content_chars


def get_rag_default_retrieval_mode() -> str:
    return get_settings().rag_default_retrieval_mode


def get_rag_vector_top_k() -> int:
    return get_settings().rag_vector_top_k


def get_rag_keyword_top_k() -> int:
    return get_settings().rag_keyword_top_k


def get_rag_fusion_top_k() -> int:
    return get_settings().rag_fusion_top_k


def get_rag_rrf_k() -> int:
    return get_settings().rag_rrf_k


def is_rag_mmr_enabled() -> bool:
    return get_settings().rag_mmr_enabled


def get_rag_mmr_lambda() -> float:
    return get_settings().rag_mmr_lambda


# Agent 相关配置函数


def get_agent_max_steps() -> int:
    return get_settings().agent_max_steps


def get_agent_allowed_tools() -> list[str]:
    raw = get_settings().agent_allowed_tools
    return [item.strip() for item in raw.split(",") if item.strip()]


def get_agent_tool_timeout_seconds() -> int:
    return get_settings().agent_tool_timeout_seconds


def get_agent_max_tool_result_chars() -> int:
    return get_settings().agent_max_tool_result_chars


def get_agent_planner_type() -> str:
    return get_settings().agent_planner_type.lower().strip()


def get_agent_planner_temperature() -> float:
    return get_settings().agent_planner_temperature


def get_agent_planner_timeout_seconds() -> int:
    return get_settings().agent_planner_timeout_seconds


def is_agent_query_rewrite_enabled() -> bool:
    return get_settings().agent_query_rewrite_enabled


def get_agent_query_rewrite_min_history() -> int:
    return get_settings().agent_query_rewrite_min_history


def get_agent_query_rewrite_short_query_chars() -> int:
    return get_settings().agent_query_rewrite_short_query_chars


def get_llm_router_model() -> str:
    return get_settings().llm_router_model


def is_mcp_enabled() -> bool:
    return get_settings().mcp_enabled


def get_mcp_allowed_tools() -> list[str]:
    raw = get_settings().mcp_allowed_tools
    return [item.strip() for item in raw.split(",") if item.strip()]


def get_mcp_max_result_chars() -> int:
    return get_settings().mcp_max_result_chars


def get_mcp_default_timeout_seconds() -> int:
    return get_settings().mcp_default_timeout_seconds


def get_context_context_token_by_config() -> int:
    return get_settings().max_context_default_tokens
