from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from src.app.services.multi_agent.role_runtime.schemas import RolePlannerDecision


class RolePlannerParseError(ValueError):
    pass


class RoleDecisionParser:
    def parse(self, content: str) -> RolePlannerDecision:
        payload = self._load_json(content)
        try:
            decision = RolePlannerDecision.model_validate(payload)
        except ValidationError as exc:
            raise RolePlannerParseError(f"Role decision schema invalid: {exc}") from exc

        if decision.type == "tool_call" and not decision.tool_name:
            raise RolePlannerParseError("tool_call requires tool_name")

        if decision.type == "final" and not decision.artifact_content:
            raise RolePlannerParseError("final requires artifact_content")

        return decision

    def _load_json(self, content: str) -> dict[str, Any]:
        clean = content.strip()
        if clean.startswith("```"):
            clean = clean.strip("`").strip()
            if clean.startswith("json"):
                clean = clean.removeprefix("json").strip()

        try:
            value = json.loads(clean)
        except json.JSONDecodeError:
            start = clean.find("{")
            end = clean.rfind("}")
            if start < 0 or end <= start:
                raise RolePlannerParseError("No JSON object found")
            value = json.loads(clean[start : end + 1])

        if not isinstance(value, dict):
            raise RolePlannerParseError("Role planner output must be JSON object")
        return value
