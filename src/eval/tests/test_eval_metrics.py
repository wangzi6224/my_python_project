from src.eval.metrics import evaluate_route_case, evaluate_agent_tool_case
from src.eval.schemas import AssistantEvalOutput, EvalCase


def test_route_eval_passes_when_mode_matches() -> None:
    case = EvalCase(
        id="route_001",
        category="route",
        message="hello",
        expected={"mode": "chat"},
    )
    output = AssistantEvalOutput(route_decision={"mode": "chat"})

    result = evaluate_route_case(case, output)

    assert result.passed is True
    assert result.score == 1


def test_route_eval_fails_when_mode_differs() -> None:
    case = EvalCase(
        id="route_002",
        category="route",
        message="search docs",
        expected={"mode": "agent"},
    )
    output = AssistantEvalOutput(route_decision={"mode": "chat"})

    result = evaluate_route_case(case, output)

    assert result.passed is False
    assert "expected mode=agent" in result.reasons[0]


def test_agent_tool_eval_checks_required_tool() -> None:
    case = EvalCase(
        id="agent_001",
        category="agent_tool",
        message="search docs",
        expected={"required_tools": ["search_docs"]},
    )
    output = AssistantEvalOutput(tool_calls=[{"tool_name": "search_docs"}])

    result = evaluate_agent_tool_case(case, output)

    assert result.passed is True
