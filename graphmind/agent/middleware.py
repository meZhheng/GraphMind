from __future__ import annotations

import ast
import json
import logging
import time
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


class ContextCompressionSwitch(MiddlewareBase):
    """Enable or disable AgentScope context compression from app config."""

    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled

    async def on_compress_context(
        self,
        agent,
        input_kwargs: dict,
        next_handler: Callable[..., Awaitable[None]],
    ) -> None:
        context_config = input_kwargs.get("context_config") or agent.context_config
        metrics = await _estimate_context_metrics(agent, context_config)
        agent.state.middle_context["current_context_tokens_estimate"] = (
            metrics["estimated_tokens"]
        )
        agent.state.middle_context["context_compression_metrics"] = metrics

        if not self.enabled:
            return

        if metrics["estimated_tokens"] < metrics["trigger_tokens"]:
            return

        started_at = time.perf_counter()
        _push_compression_event(
            agent,
            {
                "category": "compression_start",
                "title": "Compressing context",
                "content": metrics,
            },
        )

        before_summary = agent.state.summary
        before_context_count = len(agent.state.context)

        try:
            await next_handler(**input_kwargs)
        except Exception as exc:
            _push_compression_event(
                agent,
                {
                    "category": "compression_error",
                    "title": "Context compression failed",
                    "content": {
                        **metrics,
                        "error": f"{exc.__class__.__name__}: {exc}",
                    },
                },
            )
            raise

        after_metrics = await _estimate_context_metrics(agent, context_config)
        agent.state.middle_context["current_context_tokens_estimate"] = (
            after_metrics["estimated_tokens"]
        )
        agent.state.middle_context["context_compression_metrics"] = after_metrics
        changed = (
            agent.state.summary != before_summary
            or len(agent.state.context) != before_context_count
        )
        compression_result = {
            **after_metrics,
            "before_tokens": metrics["estimated_tokens"],
            "after_tokens": after_metrics["estimated_tokens"],
            "changed": changed,
            "compressed_messages": max(
                0,
                before_context_count - len(agent.state.context),
            ),
            "summary_chars": len(str(agent.state.summary or "")),
            "reserved_messages": len(agent.state.context),
            "duration_ms": round((time.perf_counter() - started_at) * 1000),
        }
        if changed:
            agent.state.middle_context["last_context_compression"] = (
                compression_result
            )
        _push_compression_event(
            agent,
            {
                "category": "compression_end",
                "title": "Context compressed",
                "content": compression_result,
            },
        )


async def _estimate_context_metrics(agent, context_config) -> dict[str, Any]:
    kwargs = await agent._prepare_model_input()
    estimated_tokens = int(await agent.model.count_tokens(**kwargs))
    context_size = int(agent.model.context_size)
    return {
        "estimated_tokens": estimated_tokens,
        "max_tokens": context_size,
        "trigger_ratio": context_config.trigger_ratio,
        "reserve_ratio": context_config.reserve_ratio,
        "trigger_tokens": int(context_config.trigger_ratio * context_size),
        "reserve_tokens": int(context_config.reserve_ratio * context_size),
        "message_count": len(kwargs.get("messages", [])),
        "tool_count": len(kwargs.get("tools", [])),
    }


def _push_compression_event(agent, payload: dict[str, Any]) -> None:
    events = agent.state.middle_context.setdefault("context_compression_events", [])
    events.append(payload)


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
