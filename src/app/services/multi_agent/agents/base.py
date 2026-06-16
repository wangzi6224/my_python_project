from __future__ import annotations

from abc import ABC, abstractmethod
from time import perf_counter
from typing import Any

from src.app.services.llm.factory import get_llm_provider
from src.app.services.multi_agent.schemas import AgentRole, RoleRunResult


class BaseRoleAgent(ABC):
    role: AgentRole
    prompt_version: str

    def __init__(self) -> None:
        self.llm_provider = get_llm_provider()

    def run_with_timing(self, **kwargs: Any) -> RoleRunResult:
        start = perf_counter()
        try:
            result = self.run(**kwargs)
            result.latency_ms = int((perf_counter() - start) * 1000)
            return result
        except Exception as exc:
            return RoleRunResult(
                role=self.role,
                status="failed",
                latency_ms=int((perf_counter() - start) * 1000),
                error_code=exc.__class__.__name__,
                error_message=str(exc),
            )

    @abstractmethod
    def run(self, **kwargs: Any) -> RoleRunResult:
        raise NotImplementedError
