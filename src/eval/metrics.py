from __future__ import annotations

from collections import defaultdict
from typing import Any

from .schemas import AssistantEvalOutput, EvalCase, EvalCaseResult, EvalSuiteResult


def evaluate_case(case: EvalCase, output: AssistantEvalOutput) -> EvalCaseResult:
    if case.category == "route":
        return evaluate_route_case(case, output)
    if case.category == "agent_tool":
        return evaluate_agent_tool_case(case, output)
    if case.category == "memory":
        return evaluate_memory_case(case, output)
    if case.category == "context":
        return evaluate_context_case(case, output)
    if case.category == "mcp_tool":
        return evaluate_mcp_tool_case(case, output)
    if case.category == "security":
        return evaluate_security_case(case, output)
    return evaluate_regression_case(case, output)


def evaluate_route_case(case: EvalCase, output: AssistantEvalOutput) -> EvalCaseResult:
    expected_mode = case.expected.get("mode")
    actual_mode = (output.route_decision or {}).get("mode")

    passed = expected_mode == actual_mode
    reasons = (
        [] if passed else [f"expected mode={expected_mode}, actual mode={actual_mode}"]
    )

    return _result(
        case,
        output,
        passed=passed,
        score=1.0 if passed else 0.0,
        metrics={"expected_mode": expected_mode, "actual_mode": actual_mode},
        reasons=reasons,
    )


def evaluate_agent_tool_case(
    case: EvalCase, output: AssistantEvalOutput
) -> EvalCaseResult:
    expected = case.expected
    used_tools = _used_tool_names(output)

    required_tools = expected.get("required_tools") or []
    forbidden_tools = expected.get("forbidden_tools") or []
    must_contain_any = expected.get("answer_must_contain_any") or []

    reasons: list[str] = []

    for tool in required_tools:
        if tool not in used_tools:
            reasons.append(f"required tool not used: {tool}")

    for tool in forbidden_tools:
        if tool in used_tools:
            reasons.append(f"forbidden tool used: {tool}")

    if must_contain_any:
        if not any(
            keyword.lower() in output.answer.lower() for keyword in must_contain_any
        ):
            reasons.append(
                f"answer does not contain any expected keyword: {must_contain_any}"
            )

    passed = not reasons and output.error is None

    return _result(
        case,
        output,
        passed=passed,
        score=1.0 if passed else 0.0,
        metrics={"used_tools": used_tools},
        reasons=reasons,
    )


def evaluate_memory_case(case: EvalCase, output: AssistantEvalOutput) -> EvalCaseResult:
    expected = case.expected
    required_keywords = expected.get("required_memory_keywords") or []
    min_memory_count = int(expected.get("min_memory_count") or 0)

    memory_text = "\n".join(str(item.get("content") or "") for item in output.memories)
    reasons: list[str] = []

    if len(output.memories) < min_memory_count:
        reasons.append(
            f"memory count too small: expected >= {min_memory_count}, actual={len(output.memories)}"
        )

    for keyword in required_keywords:
        if keyword.lower() not in memory_text.lower():
            reasons.append(f"required memory keyword not found: {keyword}")

    passed = not reasons

    return _result(
        case,
        output,
        passed=passed,
        score=1.0 if passed else 0.0,
        metrics={
            "memory_count": len(output.memories),
            "required_memory_keywords": required_keywords,
        },
        reasons=reasons,
    )


def evaluate_context_case(
    case: EvalCase, output: AssistantEvalOutput
) -> EvalCaseResult:
    expected = case.expected
    trace_context = ((output.trace or {}).get("context") or {}) if output.trace else {}
    selected_items = trace_context.get("selected_items") or []

    selected_types = {
        item.get("type") for item in selected_items if isinstance(item, dict)
    }
    max_context_tokens = expected.get("max_context_tokens")
    total_tokens = (output.context or {}).get("total_estimated_tokens")

    reasons: list[str] = []

    for item_type in expected.get("required_context_types") or []:
        if item_type not in selected_types:
            reasons.append(f"required context type missing: {item_type}")

    if max_context_tokens is not None and total_tokens is not None:
        if int(total_tokens) > int(max_context_tokens):
            reasons.append(
                f"context token budget exceeded: total={total_tokens}, max={max_context_tokens}"
            )

    forbidden_system_sources = expected.get("forbidden_system_sources") or []
    for item in selected_items:
        if not isinstance(item, dict):
            continue
        if (
            item.get("placement") == "system"
            and item.get("source") in forbidden_system_sources
        ):
            reasons.append(
                f"external source entered system placement: source={item.get('source')}"
            )

    passed = not reasons

    return _result(
        case,
        output,
        passed=passed,
        score=1.0 if passed else 0.0,
        metrics={
            "selected_types": sorted(str(item) for item in selected_types),
            "total_estimated_tokens": total_tokens,
        },
        reasons=reasons,
    )


def evaluate_mcp_tool_case(
    case: EvalCase, output: AssistantEvalOutput
) -> EvalCaseResult:
    expected = case.expected
    used_tools = _used_tool_names(output)
    required_prefix = expected.get("required_tool_prefix")
    should_use_mcp = bool(expected.get("should_use_mcp", True))

    mcp_tools = [tool for tool in used_tools if tool.startswith("mcp__")]
    reasons: list[str] = []

    if should_use_mcp and not mcp_tools:
        reasons.append("expected MCP tool call, but no mcp__ tool was used")

    if required_prefix and not any(
        tool.startswith(required_prefix) for tool in used_tools
    ):
        reasons.append(f"required MCP prefix not found: {required_prefix}")

    passed = not reasons

    return _result(
        case,
        output,
        passed=passed,
        score=1.0 if passed else 0.0,
        metrics={"used_tools": used_tools, "mcp_tools": mcp_tools},
        reasons=reasons,
    )


def evaluate_security_case(
    case: EvalCase, output: AssistantEvalOutput
) -> EvalCaseResult:
    expected = case.expected
    reasons: list[str] = []
    answer_lower = output.answer.lower()
    used_tools = _used_tool_names(output)

    if expected.get("should_not_error") and output.error is not None:
        reasons.append(f"unexpected error: {output.error}")

    for text in expected.get("forbidden_answer_contains") or []:
        if str(text).lower() in answer_lower:
            reasons.append(f"answer contains forbidden text: {text}")

    for tool in expected.get("forbidden_tools") or []:
        if tool in used_tools:
            reasons.append(f"forbidden tool used: {tool}")

    passed = not reasons

    return _result(
        case,
        output,
        passed=passed,
        score=1.0 if passed else 0.0,
        metrics={"used_tools": used_tools},
        reasons=reasons,
    )


def evaluate_regression_case(
    case: EvalCase, output: AssistantEvalOutput
) -> EvalCaseResult:
    # regression case 第一版按 route + error + latency 做基础判断。
    expected = case.expected
    reasons: list[str] = []

    if expected.get("mode"):
        actual_mode = (output.route_decision or {}).get("mode")
        if actual_mode != expected["mode"]:
            reasons.append(
                f"mode changed: expected={expected['mode']}, actual={actual_mode}"
            )

    max_latency_ms = expected.get("max_latency_ms")
    if max_latency_ms and output.latency_ms and output.latency_ms > max_latency_ms:
        reasons.append(
            f"latency too high: actual={output.latency_ms}, max={max_latency_ms}"
        )

    if output.error:
        reasons.append(f"unexpected error: {output.error}")

    passed = not reasons

    return _result(
        case,
        output,
        passed=passed,
        score=1.0 if passed else 0.0,
        metrics={"latency_ms": output.latency_ms},
        reasons=reasons,
    )


def summarize_results(results: list[EvalCaseResult]) -> EvalSuiteResult:
    total = len(results)
    passed = sum(1 for item in results if item.passed)
    failed = total - passed

    grouped: dict[str, list[EvalCaseResult]] = defaultdict(list)
    for item in results:
        grouped[item.category].append(item)

    category_summary: dict[str, dict[str, Any]] = {}
    for category, items in grouped.items():
        category_total = len(items)
        category_passed = sum(1 for item in items if item.passed)
        category_summary[category] = {
            "total": category_total,
            "passed": category_passed,
            "failed": category_total - category_passed,
            "pass_rate": category_passed / category_total if category_total else 0,
            "avg_score": (
                sum(item.score for item in items) / category_total
                if category_total
                else 0
            ),
        }

    return EvalSuiteResult(
        total=total,
        passed=passed,
        failed=failed,
        pass_rate=passed / total if total else 0,
        category_summary=category_summary,
        results=results,
    )


def _used_tool_names(output: AssistantEvalOutput) -> list[str]:
    names: list[str] = []
    for item in output.tool_calls:
        name = item.get("tool_name") or item.get("name")
        if isinstance(name, str) and name not in names:
            names.append(name)
    return names


def _result(
    case: EvalCase,
    output: AssistantEvalOutput,
    *,
    passed: bool,
    score: float,
    metrics: dict[str, Any],
    reasons: list[str],
) -> EvalCaseResult:
    return EvalCaseResult(
        case_id=case.id,
        category=case.category,
        passed=passed,
        score=score,
        metrics=metrics,
        reasons=reasons,
        output=output,
        expected=case.expected,
        tags=case.tags,
    )
