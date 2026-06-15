from __future__ import annotations

import json
from typing import Any, Iterable


def parse_sse_lines(lines: Iterable[str]) -> list[dict[str, Any]]:
    """解析 text/event-stream。

    当前后端使用：
    event: xxx
    data: {...}

    这里返回：
    {"event": "xxx", "data": {...}}
    """

    events: list[dict[str, Any]] = []
    current_event: str | None = None
    data_parts: list[str] = []

    def flush() -> None:
        nonlocal current_event, data_parts
        if current_event is None and not data_parts:
            return

        raw_data = "\n".join(data_parts).strip()
        if raw_data == "[DONE]":
            data: Any = "[DONE]"
        elif raw_data:
            try:
                data = json.loads(raw_data)
            except json.JSONDecodeError:
                data = raw_data
        else:
            data = None

        events.append({"event": current_event or "message", "data": data})
        current_event = None
        data_parts = []

    for line in lines:
        line = line.rstrip("\n")

        if not line:
            flush()
            continue

        if line.startswith("event:"):
            current_event = line.removeprefix("event:").strip()
            continue

        if line.startswith("data:"):
            data_parts.append(line.removeprefix("data:").strip())
            continue

    flush()
    return events
