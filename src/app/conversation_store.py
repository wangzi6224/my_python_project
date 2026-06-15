import json
import uuid
from datetime import datetime
from typing import Any, cast

from psycopg import sql

from src.app.config import get_default_llm_model, get_llm_provider_name
from src.app.db import get_connection
from src.app.exceptions import ConversationError

ALLOWED_MESSAGE_ROLES: set[str] = {"system", "user", "assistant", "tool"}

ALLOWED_CONVERSATION_UPDATE_FIELDS = {
    "title",
    "summary",
    "summarized_message_count",
    "summary_updated_at",
    "model",
    "provider",
    "status",
}


def _normalize_row(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None

    result = dict(row)

    for key in ["created_at", "updated_at", "summary_updated_at"]:
        if isinstance(result.get(key), datetime):
            result[key] = result[key].isoformat()

    if result.get("metadata") is None:
        result["metadata"] = {}

    return result


def create_conversation(
    title: str,
    model: str | None = None,
    provider: str | None = None,
) -> dict[str, Any]:
    conversation_id = str(uuid.uuid4())
    provider_name = (provider or get_llm_provider_name()).lower().strip()

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO conversations (
                    id,
                    title,
                    summary,
                    summarized_message_count,
                    summary_updated_at,
                    model,
                    provider,
                    status,
                    created_at,
                    updated_at
                )
                VALUES (
                    %(id)s,
                    %(title)s,
                    NULL,
                    0,
                    NULL,
                    %(model)s,
                    %(provider)s,
                    'active',
                    NOW(),
                    NOW()
                )
                RETURNING *
                """,
                {
                    "id": conversation_id,
                    "title": title,
                    "model": model or get_default_llm_model(provider_name),
                    "provider": provider_name,
                },
            )
            row = cur.fetchone()

        conn.commit()

    conversation = _normalize_row(cast(dict[str, Any] | None, row))

    if conversation is None:
        raise ConversationError(
            message="创建会话失败",
            status_code=500,
        )

    return conversation


def list_conversations() -> list[dict[str, Any]]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    conv.id,
                    conv.summary,
                    COALESCE(conv_states.current_goal, conv.title) AS title,
                    conv.model,
                    conv.provider,
                    conv.status,

                    conv.summarized_message_count,
                    conv.summary_updated_at,

                    conv.created_at,
                    conv.updated_at
                FROM conversations AS conv
                JOIN conversation_states AS conv_states
                    ON conv.id = conv_states.conversation_id
                ORDER BY conv.updated_at DESC;
                """)
            rows = cur.fetchall()

    conversations = [
        _normalize_row(cast(dict[str, Any], row)) for row in rows if row is not None
    ]
    return [conversation for conversation in conversations if conversation is not None]


def get_conversation(conversation_id: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM conversations
                WHERE id = %(conversation_id)s
                """,
                {"conversation_id": conversation_id},
            )
            row = cur.fetchone()

    return _normalize_row(cast(dict[str, Any] | None, row))


def update_conversation(
    conversation_id: str,
    updates: dict[str, Any],
) -> dict[str, Any]:
    invalid_fields = set(updates) - ALLOWED_CONVERSATION_UPDATE_FIELDS
    if invalid_fields:
        raise ConversationError(
            message="会话更新字段非法",
            detail=f"invalid_fields={sorted(invalid_fields)}",
            status_code=500,
        )

    with get_connection() as conn:
        with conn.cursor() as cur:
            if updates:
                set_sql = sql.SQL(", ").join(
                    sql.SQL("{} = {}").format(
                        sql.Identifier(key),
                        sql.Placeholder(key),
                    )
                    for key in updates
                )

                query = sql.SQL("""
                    UPDATE conversations
                    SET {set_sql},
                        updated_at = NOW()
                    WHERE id = %(conversation_id)s
                    RETURNING *
                    """).format(set_sql=set_sql)

                params = {**updates, "conversation_id": conversation_id}
            else:
                query = sql.SQL("""
                    UPDATE conversations
                    SET updated_at = NOW()
                    WHERE id = %(conversation_id)s
                    RETURNING *
                    """)
                params = {"conversation_id": conversation_id}

            cur.execute(query, params)
            row = cur.fetchone()

        conn.commit()

    conversation = _normalize_row(cast(dict[str, Any] | None, row))

    if conversation is None:
        raise ConversationError(
            message="会话不存在",
            detail=f"conversation_id={conversation_id}",
            status_code=404,
        )

    return conversation


def create_message(
    conversation_id: str,
    role: str,
    content: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if role not in ALLOWED_MESSAGE_ROLES:
        raise ConversationError(
            message="非法消息角色",
            detail=f"role={role}",
            status_code=400,
        )

    message_id = str(uuid.uuid4())

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO messages (
                    id,
                    conversation_id,
                    role,
                    content,
                    metadata,
                    created_at
                )
                VALUES (
                    %(id)s,
                    %(conversation_id)s,
                    %(role)s,
                    %(content)s,
                    %(metadata)s::jsonb,
                    NOW()
                )
                RETURNING *
                """,
                {
                    "id": message_id,
                    "conversation_id": conversation_id,
                    "role": role,
                    "content": content,
                    "metadata": json.dumps(metadata or {}, ensure_ascii=False),
                },
            )
            row = cur.fetchone()

            cur.execute(
                """
                UPDATE conversations
                SET updated_at = NOW()
                WHERE id = %(conversation_id)s
                """,
                {"conversation_id": conversation_id},
            )

        conn.commit()

    message = _normalize_message(cast(dict[str, Any] | None, row))

    if message is None:
        raise ConversationError(
            message="创建消息失败",
            status_code=500,
        )

    return message


def _normalize_message(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None

    result = dict(row)

    if isinstance(result.get("created_at"), datetime):
        result["created_at"] = result["created_at"].isoformat()

    if result.get("metadata") is None:
        result["metadata"] = {}

    return result


def list_messages(conversation_id: str) -> list[dict[str, Any]]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM messages
                WHERE conversation_id = %(conversation_id)s
                ORDER BY created_at ASC
                """,
                {"conversation_id": conversation_id},
            )
            rows = cur.fetchall()

    messages = [
        _normalize_message(cast(dict[str, Any], row)) for row in rows if row is not None
    ]
    return [message for message in messages if message is not None]


def list_recent_messages(
    conversation_id: str,
    limit: int = 10,
) -> list[dict[str, Any]]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM messages
                WHERE conversation_id = %(conversation_id)s
                ORDER BY created_at DESC
                LIMIT %(limit)s
                """,
                {
                    "conversation_id": conversation_id,
                    "limit": limit,
                },
            )
            rows = cur.fetchall()

    messages = [
        _normalize_message(cast(dict[str, Any], row)) for row in rows if row is not None
    ]

    return [message for message in reversed(messages) if message is not None]


def delete_conversation(conversation_id: str) -> bool:
    with get_connection() as conn:
        with conn.cursor() as cur:
            # 先删除关联的 Agent 事件、步骤和运行记录
            cur.execute(
                """
                DELETE FROM agent_events
                WHERE run_id IN (
                    SELECT id FROM agent_runs
                    WHERE conversation_id = %(conversation_id)s
                )
                """,
                {"conversation_id": conversation_id},
            )

            cur.execute(
                """
                DELETE FROM agent_steps
                WHERE run_id IN (
                    SELECT id FROM agent_runs
                    WHERE conversation_id = %(conversation_id)s
                )
                """,
                {"conversation_id": conversation_id},
            )

            cur.execute(
                """
                DELETE FROM agent_runs
                WHERE conversation_id = %(conversation_id)s
                """,
                {"conversation_id": conversation_id},
            )

            # 删除消息
            cur.execute(
                """
                DELETE FROM messages
                WHERE conversation_id = %(conversation_id)s
                """,
                {"conversation_id": conversation_id},
            )

            # 删除会话本身
            cur.execute(
                """
                DELETE FROM conversations
                WHERE id = %(conversation_id)s
                """,
                {"conversation_id": conversation_id},
            )

            deleted = cur.rowcount

        conn.commit()

    return deleted > 0


def count_messages(conversation_id: str) -> int:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) AS count
                FROM messages
                WHERE conversation_id = %(conversation_id)s
                """,
                {"conversation_id": conversation_id},
            )
            row = cur.fetchone()

    count_row = cast(dict[str, Any] | None, row)
    return int(count_row["count"]) if count_row else 0
