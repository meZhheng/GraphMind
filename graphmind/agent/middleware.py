from __future__ import annotations

import ast
import json
import logging
from collections.abc import AsyncGenerator, Awaitable, Callable
from typing import Any

from agentscope.message import Msg, ToolCallBlock
from agentscope.middleware import MiddlewareBase


logger = logging.getLogger("uvicorn.error")


class ToolCallArgumentSanitizer(MiddlewareBase):
    """Normalize historical tool-call arguments before OpenAI/vLLM calls."""

    async def on_model_call(
        self,
        agent,
        input_kwargs: dict,
        next_handler: Callable[
            ...,
            Awaitable[Any | AsyncGenerator[Any, None]],
        ],
    ) -> Any | AsyncGenerator[Any, None]:
        messages = input_kwargs.get("messages", [])
        safe_messages = [_sanitize_message(message) for message in messages]
        return await next_handler(**{**input_kwargs, "messages": safe_messages})


def _sanitize_message(message: Msg) -> Msg:
    copied: Msg | None = None

    for index, block in enumerate(message.content):
        if not isinstance(block, ToolCallBlock):
            continue

        normalized = _normalize_tool_arguments(block.input)
        if normalized == block.input:
            continue

        if copied is None:
            copied = message.model_copy(deep=True)

        copied_block = copied.content[index]
        if isinstance(copied_block, ToolCallBlock):
            logger.warning(
                "Normalized malformed tool arguments for call %s (%s).",
                copied_block.id,
                copied_block.name,
            )
            copied_block.input = normalized

    return copied or message


def _normalize_tool_arguments(raw_input: str) -> str:
    raw_input = raw_input or "{}"

    try:
        parsed = json.loads(raw_input)
    except json.JSONDecodeError:
        parsed = _load_python_literal(raw_input)

    if parsed is _UNPARSEABLE:
        parsed = {"raw_input": raw_input}
    elif not isinstance(parsed, dict):
        parsed = {"value": parsed}

    return json.dumps(parsed, ensure_ascii=False, separators=(",", ":"))


_UNPARSEABLE = object()


def _load_python_literal(raw_input: str) -> Any:
    try:
        return ast.literal_eval(raw_input)
    except (SyntaxError, ValueError):
        return _UNPARSEABLE
