from agentscope.agent import Agent
from agentscope.event import (
    AgentEvent,
    ConfirmResult,
    RequireUserConfirmEvent,
    UserConfirmResultEvent,
)
from agentscope.message import UserMsg

from graphmind.agent.events import event_to_payload, format_json


class HumanConfirmationUnavailable(RuntimeError):
    """Raised when a tool call needs approval but stdin is not interactive."""


class StepPrinter:
    """Print the ReAct event stream in a readable CLI format."""

    def __init__(self) -> None:
        self._tool_inputs: dict[str, str] = {}
        self._open_text_block = False
        self._open_thinking_block = False

    def handle(self, event: AgentEvent) -> None:
        payload = event_to_payload(event)
        category = payload["category"]

        if category == "model":
            self._section(payload["title"])
        elif category == "usage":
            self._close_open_blocks()
            usage = payload["content"]
            print(
                f"\n[model usage] input={usage['input_tokens']}, "
                f"output={usage['output_tokens']}",
                flush=True,
            )
        elif category == "reasoning":
            self._close_text_block()
            self._open_thinking_block = True
            self._section("reasoning")
        elif category == "reasoning_delta":
            print(payload["content"], end="", flush=True)
        elif category == "assistant":
            self._close_thinking_block()
            self._open_text_block = True
            self._section("assistant")
        elif category == "assistant_delta":
            print(payload["content"], end="", flush=True)
        elif category == "act":
            self._close_open_blocks()
            self._tool_inputs[payload["tool_call_id"]] = ""
            self._section(payload["title"])
        elif category == "act_delta":
            tool_call_id = payload["tool_call_id"]
            self._tool_inputs[tool_call_id] = (
                self._tool_inputs.get(tool_call_id, "") + payload["content"]
            )
        elif category == "act_end":
            raw_input = self._tool_inputs.pop(payload["tool_call_id"], "")
            print(format_json(raw_input), flush=True)
        elif category == "confirm":
            self._close_open_blocks()
            self._section("human-in-loop")
            for tool_call in payload["tool_calls"]:
                print(
                    f"Permission required for {tool_call['name']}:\n"
                    f"{tool_call['pretty_input']}",
                    flush=True,
                )
        elif category == "tool_response":
            self._close_open_blocks()
            self._section(payload["title"])
        elif category == "tool_response_delta":
            print(payload["content"], end="", flush=True)
        elif category == "data":
            self._section(payload["title"])
        elif category == "tool_response_end":
            print(f"\n[tool state] {payload['state']}", flush=True)
        elif category == "external_execution":
            self._section("external execution required")
            print(
                "This runner only handles local tools and user confirmation.",
                flush=True,
            )
        elif category == "stopped":
            self._section("stopped")
            print("Exceeded max ReAct iterations.", flush=True)
        elif category == "done":
            self._close_open_blocks()
            self._section("reply end")

    def _section(self, title: str) -> None:
        print(f"\n=== {title} ===", flush=True)

    def _close_text_block(self) -> None:
        if self._open_text_block:
            print("", flush=True)
            self._open_text_block = False

    def _close_thinking_block(self) -> None:
        if self._open_thinking_block:
            print("", flush=True)
            self._open_thinking_block = False

    def _close_open_blocks(self) -> None:
        self._close_text_block()
        self._close_thinking_block()


def ask_user_confirmation(event: RequireUserConfirmEvent) -> UserConfirmResultEvent:
    confirm_results = []
    for tool_call in event.tool_calls:
        try:
            answer = input(f"Allow {tool_call.name}? [y/N]: ").strip().lower()
        except EOFError:
            raise HumanConfirmationUnavailable(
                "Human confirmation is required, but no interactive input "
                "is available.",
            ) from None
        confirm_results.append(
            ConfirmResult(
                confirmed=answer in {"y", "yes"},
                tool_call=tool_call,
                rules=None,
            ),
        )

    return UserConfirmResultEvent(
        reply_id=event.reply_id,
        confirm_results=confirm_results,
    )


async def run_agent_cli(agent: Agent, task: UserMsg) -> None:
    printer = StepPrinter()
    next_input: UserMsg | UserConfirmResultEvent | None = task

    while True:
        confirmation_event: UserConfirmResultEvent | None = None
        async for event in agent.reply_stream(next_input):
            printer.handle(event)
            if isinstance(event, RequireUserConfirmEvent):
                confirmation_event = ask_user_confirmation(event)

        if confirmation_event is None:
            break
        next_input = confirmation_event
