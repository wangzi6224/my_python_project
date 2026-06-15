from typing import Any, Literal
from pydantic import BaseModel, Field
from src.app.config import get_agent_max_steps
from src.app.services.memory.working_memory import WorkingMemory


class AgentObservation(BaseModel):
    # 观察来自哪个步骤
    step: int
    # 工具名称
    tool_name: str
    # 工具参数
    arguments: dict[str, Any] = Field(default_factory=dict)
    # 工具是否执行成功
    success: bool
    # 经过长度限制后的工具结果
    result: dict[str, Any] | None = None
    # 错误码
    error_code: str | None = None
    # 错误消息
    error_message: str | None = None


class AgentStep(BaseModel):
    # 当前步骤编号
    step: int
    # 步骤类型：工具调用、最终结果、最终答案或错误
    type: Literal["tool_call", "final", "final_answer", "error"]
    # 使用的工具名称（如果有）
    tool_name: str | None = None
    # 传递给工具的参数
    arguments: dict[str, Any] = Field(default_factory=dict)
    # 工具执行或步骤结果
    result: dict[str, Any] | None = None
    # 当前步骤是否成功
    success: bool = True
    # 当前步骤的延迟，单位毫秒
    latency_ms: int = 0
    # 如果失败或需要解释，则记录原因
    reason: str | None = None
    # 错误代码
    error_code: str | None = None
    # 错误消息描述
    error_message: str | None = None


class AgentState(BaseModel):
    # 运行ID
    run_id: str
    # 会话ID
    conversation_id: str
    # 用户消息ID
    user_message_id: str
    # 用户问题
    question: str
    # 用户原始问题，保留用于审计、最终回答和消息展示
    original_question: str | None = None
    # 改写后的规划/检索问题，仅用于辅助 planner 和工具检索
    rewritten_question: str | None = None
    # Query rewrite 执行结果和降级原因
    query_rewrite: dict[str, Any] | None = None
    # 消息列表
    messages: list[dict[str, Any]]
    # 步骤列表
    steps: list[AgentStep] = Field(default_factory=list)
    # 观察列表
    observations: list[AgentObservation] = Field(default_factory=list)
    # 最大步骤数
    max_steps: int = Field(default_factory=get_agent_max_steps)
    # 模型名称
    model: str
    # top_k 参数
    top_k: int = 5
    # 分数阈值
    score_threshold: float = 0.3
    # 结束原因
    finish_reason: str | None = None
    # Planner 类型
    planner_type: str = "llm"
    # Planner 提示词版本
    planner_prompt_version: str | None = None
    # Planner 产出决策次数
    planner_decision_count: int = 0
    # Planner 异常后使用兜底决策次数
    planner_fallback_count: int = 0
    # 工作记忆
    working_memory: WorkingMemory = Field(default_factory=WorkingMemory)
    # LLMOps trace id，由 AssistantOrchestrator 传入；为空时跳过 span 写入
    trace_id: str | None = None
    # AgentService 创建的 agent.run span id，工具 span 挂在它下面
    agent_span_id: str | None = None
    # 上游父 span id，通常是 assistant.run root span
    parent_span_id: str | None = None
    # Assistant run id，用于关联 assistant_runs 和 trace_spans
    assistant_run_id: str | None = None
