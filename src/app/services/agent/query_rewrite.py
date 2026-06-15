from __future__ import annotations

from typing import Any

from src.app.config import (
    get_agent_query_rewrite_min_history,
    get_agent_query_rewrite_short_query_chars,
    is_agent_query_rewrite_enabled,
)


REFERENCE_WORDS = (
    "这个",
    "那个",
    "它",
    "他们",
    "她们",
    "这些",
    "那些",
    "上面",
    "前面",
    "刚才",
    "刚刚",
    "继续",
    "再说",
    "详细点",
    "展开",
    "对比",
    "之前",
    "上一",
)

SHORT_FOLLOW_UP_WORDS = (
    "怎么改",
    "怎么做",
    "继续",
    "详细说",
    "展开",
    "为什么",
    "然后呢",
    "有吗",
)


def count_user_messages(messages: list[dict[str, Any]]) -> int:
    return sum(1 for item in messages if item.get("role") == "user")


def has_reference_words(question: str) -> bool:
    return any(word in question for word in REFERENCE_WORDS)


def is_short_followup(question: str) -> bool:
    compact = "".join(question.split())
    if len(compact) <= get_agent_query_rewrite_short_query_chars():
        return True
    return any(word in question for word in SHORT_FOLLOW_UP_WORDS)


def should_rewrite_agent_query(
    *,
    question: str,
    recent_messages: list[dict[str, Any]],
) -> bool:
    if not is_agent_query_rewrite_enabled():
        return False

    if count_user_messages(recent_messages) < get_agent_query_rewrite_min_history():
        return False

    return has_reference_words(question) or is_short_followup(question)


def skipped_query_rewrite(question: str, reason: str) -> dict[str, Any]:
    return {
        "original_query": question,
        "rewritten_query": question,
        "rewrite_changed": False,
        "latency_ms": 0,
        "fallback_reason": reason,
    }


def normalize_query_rewrite_result(
    *,
    question: str,
    rewrite_result: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    rewritten_question = str(rewrite_result.get("rewritten_query") or question).strip()
    if rewritten_question:
        return rewritten_question, rewrite_result

    normalized = {
        **rewrite_result,
        "rewritten_query": question,
        "rewrite_changed": False,
        "fallback_reason": rewrite_result.get("fallback_reason")
        or "EMPTY_REWRITE_RESULT",
    }
    return question, normalized
