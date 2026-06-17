from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from src.app.services.multi_agent.coordinator.schemas import CoordinatorDecision


class CoordinatorDecisionParseError(ValueError):
    pass


class CoordinatorDecisionParser:
    """解析 CoordinatorPlanner 的 JSON 输出。"""

    def parse(self, content: str) -> CoordinatorDecision:
        payload = self._load_json(content)
        payload = self._normalize_payload(payload)

        try:
            decision = CoordinatorDecision.model_validate(payload)
        except ValidationError as exc:
            raise CoordinatorDecisionParseError(
                f"Coordinator decision schema invalid: {exc}"
            ) from exc

        self._validate_semantics(decision)
        return decision

    def _normalize_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        """清理模型为无关字段生成的宽松值，保留动作相关语义。"""
        normalized = dict(payload)
        decision_type = normalized.get("type")
        review_feedback = normalized.get("review_feedback")

        if decision_type != "revise_role":
            # final/run_role 等动作不会消费 review_feedback，不应被无关字段阻断。
            normalized["review_feedback"] = None
        elif isinstance(review_feedback, str):
            normalized["review_feedback"] = {"summary": review_feedback}
        elif isinstance(review_feedback, list):
            normalized["review_feedback"] = {"items": review_feedback}

        return normalized

    def _load_json(self, content: str) -> dict[str, Any]:
        clean = content.strip()

        if clean.startswith("```"):
            clean = clean.strip("`").strip()
            if clean.startswith("json"):
                clean = clean.removeprefix("json").strip()

        try:
            value = json.loads(clean)
        except json.JSONDecodeError:
            value = self._extract_json_object(clean)

        if not isinstance(value, dict):
            raise CoordinatorDecisionParseError("Coordinator output must be a JSON object")

        return value

    def _extract_json_object(self, text: str) -> dict[str, Any]:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise CoordinatorDecisionParseError("No JSON object found")

        raw = text[start : end + 1]
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise CoordinatorDecisionParseError(f"Invalid JSON: {exc}") from exc

        if not isinstance(value, dict):
            raise CoordinatorDecisionParseError("Extracted JSON is not an object")

        return value

    def _validate_semantics(self, decision: CoordinatorDecision) -> None:
        if decision.type in ("run_role", "revise_role", "request_review"):
            if decision.role is None:
                raise CoordinatorDecisionParseError(
                    f"{decision.type} requires role"
                )
            if not decision.task_objective:
                raise CoordinatorDecisionParseError(
                    f"{decision.type} requires task_objective"
                )

        if decision.type == "revise_role":
            if not decision.revision_of_artifact_id:
                raise CoordinatorDecisionParseError(
                    "revise_role requires revision_of_artifact_id"
                )
            if not decision.review_feedback:
                raise CoordinatorDecisionParseError(
                    "revise_role requires review_feedback"
                )

        if decision.type == "skip_role" and decision.target_role is None:
            raise CoordinatorDecisionParseError("skip_role requires target_role")

        if decision.type == "fail" and not decision.failure_message:
            raise CoordinatorDecisionParseError("fail requires failure_message")
