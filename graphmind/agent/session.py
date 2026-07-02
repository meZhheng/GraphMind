from __future__ import annotations

from dataclasses import dataclass, field

from agentscope.agent import Agent
from agentscope.event import (
    ConfirmResult,
    ModelCallEndEvent,
    RequireUserConfirmEvent,
    UserConfirmResultEvent,
)
from agentscope.message import UserMsg

from graphmind.agent.events import event_to_payload
from graphmind.agent.factory import build_code_agent


@dataclass
class AgentSession:
    id: str
    agent: Agent = field(default_factory=build_code_agent)
    pending_confirmation: RequireUserConfirmEvent | None = None
    current_context_tokens: int = 0

    async def stream_task(self, content: str):
        self.pending_confirmation = None
        async for payload in self._stream_agent(
            UserMsg(name="user", content=content),
        ):
            yield payload

    async def stream_confirmation(self, results: list[dict]):
        if self.pending_confirmation is None:
            yield {
                "category": "error",
                "title": "No pending confirmation",
                "content": "There is no tool call waiting for confirmation.",
            }
            return

        tool_calls = {call.id: call for call in self.pending_confirmation.tool_calls}
        confirm_results = []
        for item in results:
            tool_call_id = item.get("tool_call_id")
            if tool_call_id not in tool_calls:
                continue
            confirm_results.append(
                ConfirmResult(
                    confirmed=bool(item.get("confirmed")),
                    tool_call=tool_calls[tool_call_id],
                    rules=None,
                ),
            )

        event = UserConfirmResultEvent(
            reply_id=self.pending_confirmation.reply_id,
            confirm_results=confirm_results,
        )
        self.pending_confirmation = None

        async for payload in self._stream_agent(event):
            yield payload

    async def _stream_agent(self, next_input):
        confirmation_seen = False
        async for event in self.agent.reply_stream(next_input):
            if isinstance(event, ModelCallEndEvent):
                self.current_context_tokens = event.input_tokens

            payload = event_to_payload(event)
            payload["context"] = {
                "current_tokens": self.current_context_tokens,
                "max_tokens": self.agent.model.context_size,
            }
            yield payload

            if isinstance(event, RequireUserConfirmEvent):
                self.pending_confirmation = event
                confirmation_seen = True

        if not confirmation_seen:
            self.pending_confirmation = None
