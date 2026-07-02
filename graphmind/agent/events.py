import json
from typing import Any

from agentscope.event import (
    AgentEvent,
    DataBlockDeltaEvent,
    ExceedMaxItersEvent,
    ModelCallEndEvent,
    ModelCallStartEvent,
    RequireExternalExecutionEvent,
    RequireUserConfirmEvent,
    ReplyEndEvent,
    TextBlockDeltaEvent,
    TextBlockStartEvent,
    ThinkingBlockDeltaEvent,
    ThinkingBlockStartEvent,
    ToolCallDeltaEvent,
    ToolCallEndEvent,
    ToolCallStartEvent,
    ToolResultEndEvent,
    ToolResultStartEvent,
    ToolResultTextDeltaEvent,
)


def format_json(raw_input: str) -> str:
    try:
        return json.dumps(
            json.loads(raw_input),
            ensure_ascii=False,
            indent=2,
        )
    except json.JSONDecodeError:
        return raw_input or "{}"


def event_to_payload(event: AgentEvent) -> dict[str, Any]:
    payload = {
        "type": getattr(event, "type", event.__class__.__name__),
        "event": event.model_dump(mode="json", exclude_none=True),
    }

    if isinstance(event, ModelCallStartEvent):
        payload.update(
            category="model",
            title=f"Model call: {event.model_name}",
        )
    elif isinstance(event, ModelCallEndEvent):
        payload.update(
            category="usage",
            title="Model usage",
            content={
                "input_tokens": event.input_tokens,
                "output_tokens": event.output_tokens,
            },
        )
    elif isinstance(event, ThinkingBlockStartEvent):
        payload.update(category="reasoning", title="Reasoning")
    elif isinstance(event, ThinkingBlockDeltaEvent):
        payload.update(category="reasoning_delta", content=event.delta)
    elif isinstance(event, TextBlockStartEvent):
        payload.update(category="assistant", title="Assistant")
    elif isinstance(event, TextBlockDeltaEvent):
        payload.update(category="assistant_delta", content=event.delta)
    elif isinstance(event, ToolCallStartEvent):
        payload.update(
            category="act",
            title=f"Act: {event.tool_call_name}",
            tool_call_id=event.tool_call_id,
            tool_name=event.tool_call_name,
        )
    elif isinstance(event, ToolCallDeltaEvent):
        payload.update(
            category="act_delta",
            content=event.delta,
            tool_call_id=event.tool_call_id,
        )
    elif isinstance(event, ToolCallEndEvent):
        payload.update(
            category="act_end",
            tool_call_id=event.tool_call_id,
        )
    elif isinstance(event, RequireUserConfirmEvent):
        payload.update(
            category="confirm",
            title="Human confirmation required",
            tool_calls=[
                {
                    "id": call.id,
                    "name": call.name,
                    "input": call.input,
                    "pretty_input": format_json(call.input),
                }
                for call in event.tool_calls
            ],
        )
    elif isinstance(event, ToolResultStartEvent):
        payload.update(
            category="tool_response",
            title=f"Tool response: {event.tool_call_name}",
            tool_call_id=event.tool_call_id,
            tool_name=event.tool_call_name,
        )
    elif isinstance(event, ToolResultTextDeltaEvent):
        payload.update(
            category="tool_response_delta",
            content=event.delta,
            tool_call_id=event.tool_call_id,
        )
    elif isinstance(event, DataBlockDeltaEvent):
        payload.update(
            category="data",
            title=f"Data block: {event.media_type}",
            content={"media_type": event.media_type},
        )
    elif isinstance(event, ToolResultEndEvent):
        payload.update(
            category="tool_response_end",
            state=event.state,
            tool_call_id=event.tool_call_id,
        )
    elif isinstance(event, RequireExternalExecutionEvent):
        payload.update(
            category="external_execution",
            title="External execution required",
        )
    elif isinstance(event, ExceedMaxItersEvent):
        payload.update(category="stopped", title="Exceeded max iterations")
    elif isinstance(event, ReplyEndEvent):
        payload.update(category="done", title="Reply end")
    else:
        payload.update(category="event", title=payload["type"])

    return payload
