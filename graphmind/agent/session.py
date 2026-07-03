from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
from typing import Any

from agentscope.agent import Agent
from agentscope.event import (
    AgentEvent,
    ConfirmResult,
    ModelCallEndEvent,
    RequireUserConfirmEvent,
    UserConfirmResultEvent,
)
from agentscope.message import UserMsg

from graphmind.agent.events import event_to_payload
from graphmind.agent.factory import build_code_agent


logger = logging.getLogger("uvicorn.error")


@dataclass
class AgentSession:
    id: str
    agent: Agent = field(default_factory=build_code_agent)
    pending_confirmation: RequireUserConfirmEvent | None = None
    current_context_tokens: int = 0
    last_model_input_tokens: int = 0
    is_running: bool = False
    last_event: str = "created"
    last_active_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
    )

    @property
    def context_payload(self) -> dict:
        compression_settings = self.agent.state.middle_context.get(
            "last_context_compression",
            {},
        )
        compression_metrics = self.agent.state.middle_context.get(
            "context_compression_metrics",
            {},
        )
        estimated_tokens = self.agent.state.middle_context.get(
            "current_context_tokens_estimate",
        )
        current_tokens = int(
            estimated_tokens
            if estimated_tokens is not None
            else self.current_context_tokens,
        )
        max_tokens = int(self.agent.model.context_size)
        trigger_ratio = self.agent.context_config.trigger_ratio
        reserve_ratio = self.agent.context_config.reserve_ratio
        return {
            "current_tokens": current_tokens,
            "last_model_input_tokens": self.last_model_input_tokens,
            "max_tokens": max_tokens,
            "compression": {
                "enabled": bool(
                    self.agent.state.middle_context.get(
                        "context_compression_enabled",
                        False,
                    ),
                ),
                "trigger_ratio": trigger_ratio,
                "reserve_ratio": reserve_ratio,
                "trigger_tokens": int(trigger_ratio * max_tokens),
                "reserve_tokens": int(reserve_ratio * max_tokens),
                "tool_result_limit": self.agent.context_config.tool_result_limit,
                "has_summary": bool(self.agent.state.summary),
                "summary_chars": len(str(self.agent.state.summary or "")),
                **compression_metrics,
                **compression_settings,
            },
        }

    @property
    def pending_confirmation_payload(self) -> dict | None:
        if self.pending_confirmation is None:
            return None
        return event_to_payload(self.pending_confirmation)

    @property
    def status_payload(self) -> dict:
        return {
            "is_running": self.is_running,
            "is_awaiting_confirmation": self.pending_confirmation is not None,
            "pending_confirmation_count": len(
                self.pending_confirmation.tool_calls,
            )
            if self.pending_confirmation is not None
            else 0,
            "last_event": self.last_event,
            "last_active_at": self.last_active_at,
        }

    def _touch(self, event: AgentEvent | str) -> None:
        self.last_active_at = datetime.now(timezone.utc).isoformat()
        if isinstance(event, str):
            self.last_event = event
        else:
            self.last_event = event.__class__.__name__

    def _merge_pending_confirmation(
        self,
        event: RequireUserConfirmEvent,
    ) -> RequireUserConfirmEvent:
        if (
            self.pending_confirmation is None
            or self.pending_confirmation.reply_id != event.reply_id
        ):
            self.pending_confirmation = event
            return event

        existing_calls = {
            call.id: call for call in self.pending_confirmation.tool_calls
        }
        for call in event.tool_calls:
            existing_calls.setdefault(call.id, call)

        self.pending_confirmation = RequireUserConfirmEvent(
            reply_id=event.reply_id,
            tool_calls=list(existing_calls.values()),
        )
        return self.pending_confirmation

    async def stream_task(self, content: str):
        if self.pending_confirmation is not None:
            yield {
                "category": "error",
                "title": "Pending approval",
                "content": (
                    "The agent is waiting for a human approval. "
                    "Please allow or deny the pending tool call before sending "
                    "a new message."
                ),
                "pending_confirmation": self.pending_confirmation_payload,
                "context": self.context_payload,
                "session_status": self.status_payload,
            }
            return

        if self.is_running:
            yield {
                "category": "error",
                "title": "Agent is running",
                "content": "The agent is still processing the previous request.",
                "context": self.context_payload,
                "session_status": self.status_payload,
            }
            return

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
                "context": self.context_payload,
                "session_status": self.status_payload,
            }
            return

        if self.is_running:
            yield {
                "category": "error",
                "title": "Agent is running",
                "content": "The agent is already processing a confirmation.",
                "context": self.context_payload,
                "session_status": self.status_payload,
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
        self.is_running = True
        self._touch("running")
        event_queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()

        async def collect_agent_events() -> None:
            try:
                async for event in self.agent.reply_stream(next_input):
                    await event_queue.put(("event", event))
            except Exception as exc:  # pragma: no cover - re-raised below
                await event_queue.put(("error", exc))
            finally:
                await event_queue.put(("done", None))

        agent_task = asyncio.create_task(collect_agent_events())
        try:
            agent_done = False
            while not agent_done or not event_queue.empty():
                for payload in self._drain_compression_payloads():
                    yield payload

                try:
                    kind, item = await asyncio.wait_for(
                        event_queue.get(),
                        timeout=0.1,
                    )
                except TimeoutError:
                    continue

                for payload in self._drain_compression_payloads():
                    yield payload

                if kind == "done":
                    agent_done = True
                    continue
                if kind == "error":
                    raise item

                event = item
                self._touch(event)
                if isinstance(event, ModelCallEndEvent):
                    self.current_context_tokens = event.input_tokens
                    self.last_model_input_tokens = event.input_tokens
                    self.agent.state.middle_context[
                        "current_context_tokens_estimate"
                    ] = event.input_tokens

                if isinstance(event, RequireUserConfirmEvent):
                    event = self._merge_pending_confirmation(event)
                    confirmation_seen = True
                    self.is_running = False

                payload = event_to_payload(event)
                payload["context"] = self.context_payload
                payload["session_status"] = self.status_payload
                logger.info(
                    "session=%s event=%s pending=%s running=%s",
                    self.id,
                    self.last_event,
                    self.status_payload["pending_confirmation_count"],
                    self.is_running,
                )
                yield payload
        except Exception as exc:
            self._touch("error")
            self.is_running = False
            logger.exception(
                "session=%s failed after event=%s",
                self.id,
                self.last_event,
            )
            yield {
                "category": "error",
                "title": "Agent failed",
                "content": f"{exc.__class__.__name__}: {exc}",
                "context": self.context_payload,
                "session_status": self.status_payload,
            }
        finally:
            if not agent_task.done():
                agent_task.cancel()
                try:
                    await agent_task
                except asyncio.CancelledError:
                    pass
            for payload in self._drain_compression_payloads():
                yield payload
            if not confirmation_seen:
                self.pending_confirmation = None
                self.is_running = False
                self._touch("idle")

    def _drain_compression_payloads(self) -> list[dict]:
        events = self.agent.state.middle_context.get(
            "context_compression_events",
            [],
        )
        if not events:
            return []

        self.agent.state.middle_context["context_compression_events"] = []
        payloads = []
        for event in events:
            payload = {
                "type": event.get("category", "compression"),
                "category": event.get("category", "compression"),
                "title": event.get("title", "Context compression"),
                "content": event.get("content", {}),
                "context": self.context_payload,
                "session_status": self.status_payload,
            }
            payloads.append(payload)
        return payloads
