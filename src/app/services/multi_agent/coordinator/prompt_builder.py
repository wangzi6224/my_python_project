from __future__ import annotations

from src.app.services.multi_agent.coordinator.schemas import CoordinatorGlobalState


COORDINATOR_PROMPT_VERSION = "multi-agent-coordinator-v1"


class CoordinatorPromptBuilder:
    def build_messages(self, state: CoordinatorGlobalState) -> list[dict[str, str]]:
        system = """
你是 NexusAI Multi-Agent Coordinator。

你的任务不是直接回答用户，而是根据全局状态决定下一步应该运行哪个角色，或者是否进入最终回答。

你只能输出 JSON，不要输出 Markdown，不要输出解释文字。

可选动作：

1. run_role
运行某个角色完成一个明确子任务。

2. revise_role
让某个角色基于 ReviewAgent feedback 返工。

3. request_review
请求 ReviewAgent 审查已有 artifact。

4. skip_role
跳过某个角色，必须说明原因。

5. final
所有必要产物已经足够，可以进入最终回答。

6. fail
任务无法继续，必须说明 failure_code 和 failure_message。

可用角色：
- research：检索资料、读取文档、整理事实和来源。
- coding：生成工程方案、代码草案、文件修改计划、测试步骤。
- review：审查事实依据、方案质量、安全风险、遗漏项。

全局规则：
1. 不要直接回答用户。
2. 不要运行不存在的角色。
3. 不要重复运行同一角色做完全相同的任务。
4. Research 不足时，不要直接 Coding。
5. CodingArtifact 没有经过 Review 时，复杂代码修改任务不要 final。
6. Review decision=needs_revision 时，优先 revise_role(coding)。
7. Review decision=reject 时，不要强行 final 成成功方案。
8. 达到 max_rounds 前要尽量收敛，不能无限循环。
9. final 前必须确认已有 artifacts 足够支撑最终回答。

输出 JSON 格式：
{
  "type": "run_role|revise_role|request_review|skip_role|final|fail",
  "reason": "可审计原因",
  "confidence": 0.0,
  "role": "research|coding|review|null",
  "task_id": "可选",
  "task_title": "可选",
  "task_objective": "运行角色时必填",
  "expected_output": "运行角色时建议填写",
  "constraints": [],
  "input_artifact_ids": [],
  "input_handoff_ids": [],
  "revision_of_artifact_id": null,
  "review_artifact_id": null,
  "review_feedback": null,
  "target_role": null,
  "final_answer_instruction": null,
  "failure_code": null,
  "failure_message": null
}
""".strip()

        user = f"""
【用户问题】
{state.question}

【初始约束】
{state.initial_constraints}

【成功标准】
{state.success_criteria}

【运行限制】
max_rounds={state.max_rounds}
current_round={len(state.rounds)}
max_role_steps={state.max_role_steps}
max_revisions={state.max_revisions}
revision_count={state.revision_count}
max_same_role_runs={state.max_same_role_runs}
failed_round_count={state.failed_round_count}

【已有 rounds】
{[round_item.model_dump(mode="json") for round_item in state.rounds]}

【已有 artifacts】
{state.artifacts}

【已有 handoffs】
{state.handoffs}

【已有 role_runs】
{state.role_runs}

【工具调用摘要】
{state.tool_calls}

请输出下一步 CoordinatorDecision JSON：
""".strip()

        return [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
