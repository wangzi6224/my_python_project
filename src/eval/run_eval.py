from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.eval.assistant_client import AssistantEvalClient
from src.eval.metrics import evaluate_case, summarize_results
from src.eval.report import write_markdown_report
from src.eval.schemas import EvalCase, EvalRunConfig


def load_cases(path: str | Path) -> list[EvalCase]:
    cases: list[EvalCase] = []
    for line_no, line in enumerate(
        Path(path).read_text(encoding="utf-8").splitlines(), start=1
    ):
        clean = line.strip()
        if not clean or clean.startswith("#"):
            continue
        try:
            cases.append(EvalCase.model_validate_json(clean))
        except Exception as exc:
            raise ValueError(f"Invalid eval case at {path}:{line_no}: {exc}") from exc
    return cases


def main() -> None:
    parser = argparse.ArgumentParser(description="Run NexusAI assistant eval")
    parser.add_argument("--dataset", required=True, help="JSONL dataset path")
    parser.add_argument("--conversation-id", required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--model", default=None)
    parser.add_argument("--provider", default=None)
    parser.add_argument("--report", default="src/eval/reports/report.md")
    parser.add_argument("--result-json", default="src/eval/results/latest.json")
    parser.add_argument("--fail-fast", action="store_true")
    args = parser.parse_args()

    config = EvalRunConfig(
        base_url=args.base_url,
        conversation_id=args.conversation_id,
        model=args.model,
        provider=args.provider,
        fail_fast=args.fail_fast,
    )

    cases = load_cases(args.dataset)
    client = AssistantEvalClient(config)

    results = []
    for case in cases:
        print(f"[eval] running {case.id} ({case.category})")
        try:
            output = client.run_case(case)
            result = evaluate_case(case, output)
        except Exception as exc:
            # Runner 自身异常也要进入结果，避免一条 case 中断全部评测。
            from src.eval.schemas import AssistantEvalOutput, EvalCaseResult

            result = EvalCaseResult(
                case_id=case.id,
                category=case.category,
                passed=False,
                score=0,
                metrics={},
                reasons=[f"runner error: {exc}"],
                output=AssistantEvalOutput(
                    error={"code": exc.__class__.__name__, "message": str(exc)}
                ),
                expected=case.expected,
                tags=case.tags,
            )

        results.append(result)
        if args.fail_fast and not result.passed:
            break

    suite = summarize_results(results)

    result_path = Path(args.result_json)
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(
        json.dumps(suite.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    write_markdown_report(suite, args.report)

    print(
        f"[eval] total={suite.total} passed={suite.passed} failed={suite.failed} pass_rate={suite.pass_rate:.2%}"
    )
    print(f"[eval] report={args.report}")
    print(f"[eval] result_json={args.result_json}")


if __name__ == "__main__":
    main()
