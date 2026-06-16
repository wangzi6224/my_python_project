from __future__ import annotations

from src.app.services.llm.factory import get_llm_provider
from src.app.services.multi_agent.prompts import FINAL_SYNTHESIZER_SYSTEM_PROMPT
from src.app.services.multi_agent.schemas import AgentArtifact


class FinalSynthesizer:
    def __init__(self) -> None:
        self.llm_provider = get_llm_provider()

    def synthesize(
        self,
        *,
        question: str,
        artifacts: list[AgentArtifact],
        model: str | None = None,
    ) -> str:
        artifact_text = "\n\n".join(
            f"## {item.role} / {item.artifact_type}\n{item.content}"
            for item in artifacts
        )

        response = self.llm_provider.chat(
            messages=[
                {"role": "system", "content": FINAL_SYNTHESIZER_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"用户问题：\n{question}\n\n"
                        f"多智能体中间产物：\n{artifact_text}\n\n"
                        "请给出最终回答。"
                    ),
                },
            ],
            model=model,
            thinking_enabled=False,
        )
        return response.content
