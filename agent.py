import asyncio
import json
import os
from pathlib import Path
from dotenv import load_dotenv

from agentscope.agent import Agent, ReActConfig
from agentscope.credential import OpenAICredential
from agentscope.event import (
    AgentEvent,
    ConfirmResult,
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
    UserConfirmResultEvent,
)
from agentscope.message import UserMsg
from agentscope.model import OpenAIChatModel
from agentscope.permission import (
    AdditionalWorkingDirectory,
    PermissionBehavior,
    PermissionMode,
    PermissionRule,
)
from agentscope.state import AgentState
from agentscope.tool import Bash, Edit, Glob, Grep, Read, Toolkit, Write


PROJECT_ROOT = Path(__file__).resolve().parent
ENV_PATH = PROJECT_ROOT / ".env"
FILE_RELATED_TOOLS = ("Read", "Write", "Edit", "Glob", "Grep", "Bash")
DEFAULT_TASK = (
    "请在项目根目录创建一个 README.md 文件，"
    "不要把整份 README 包在 Markdown 代码块里。"
    "请使用文件工具完成写入。"
)


class HumanConfirmationUnavailable(RuntimeError):
    """Raised when a tool call needs approval but stdin is not interactive."""


def load_env(path: Path = ENV_PATH) -> None:
    load_dotenv(dotenv_path=path, override=False)


def build_model() -> OpenAIChatModel:
    load_env()

    api_base = os.getenv("OPENAI_API_BASE")
    model_name = os.getenv("MODEL_NAME")
    if not api_base or not model_name:
        raise RuntimeError(
            "Please set OPENAI_API_BASE and MODEL_NAME in .env",
        )

    credential = OpenAICredential(
        api_key=os.getenv("OPENAI_API_KEY", "EMPTY"),
        base_url=api_base,
    )
    return OpenAIChatModel(
        credential=credential,
        model=model_name,
        stream=True,
        client_kwargs={"timeout": 60.0},
        parameters=OpenAIChatModel.Parameters(
            temperature=0.2,
            max_tokens=1024,
        ),
    )


class StepPrinter:
    """Print the ReAct event stream in a readable CLI format."""

    def __init__(self) -> None:
        self._tool_inputs: dict[str, str] = {}
        self._open_text_block = False
        self._open_thinking_block = False

    def handle(self, event: AgentEvent) -> None:
        if isinstance(event, ModelCallStartEvent):
            self._section(f"model call -> {event.model_name}")

        elif isinstance(event, ModelCallEndEvent):
            self._close_open_blocks()
            print(
                f"\n[model usage] input={event.input_tokens}, "
                f"output={event.output_tokens}",
                flush=True,
            )

        elif isinstance(event, ThinkingBlockStartEvent):
            self._close_text_block()
            self._open_thinking_block = True
            self._section("reasoning")

        elif isinstance(event, ThinkingBlockDeltaEvent):
            print(event.delta, end="", flush=True)

        elif isinstance(event, TextBlockStartEvent):
            self._close_thinking_block()
            self._open_text_block = True
            self._section("assistant")

        elif isinstance(event, TextBlockDeltaEvent):
            print(event.delta, end="", flush=True)

        elif isinstance(event, ToolCallStartEvent):
            self._close_open_blocks()
            self._tool_inputs[event.tool_call_id] = ""
            self._section(f"act -> {event.tool_call_name}")

        elif isinstance(event, ToolCallDeltaEvent):
            self._tool_inputs[event.tool_call_id] = (
                self._tool_inputs.get(event.tool_call_id, "") + event.delta
            )

        elif isinstance(event, ToolCallEndEvent):
            raw_input = self._tool_inputs.pop(event.tool_call_id, "")
            print(self._format_tool_input(raw_input), flush=True)

        elif isinstance(event, RequireUserConfirmEvent):
            self._close_open_blocks()
            self._section("human-in-loop")
            for tool_call in event.tool_calls:
                print(
                    f"Permission required for {tool_call.name}:\n"
                    f"{self._format_tool_input(tool_call.input)}",
                    flush=True,
                )

        elif isinstance(event, ToolResultStartEvent):
            self._close_open_blocks()
            self._section(f"tool response <- {event.tool_call_name}")

        elif isinstance(event, ToolResultTextDeltaEvent):
            print(event.delta, end="", flush=True)

        elif isinstance(event, DataBlockDeltaEvent):
            print(
                f"\n[data block] {event.media_type} "
                f"({len(event.data or event.url or '')} chars)",
                flush=True,
            )

        elif isinstance(event, ToolResultEndEvent):
            print(f"\n[tool state] {event.state}", flush=True)

        elif isinstance(event, RequireExternalExecutionEvent):
            self._section("external execution required")
            print(
                "This runner only handles local tools and user confirmation.",
                flush=True,
            )

        elif isinstance(event, ExceedMaxItersEvent):
            self._section("stopped")
            print("Exceeded max ReAct iterations.", flush=True)

        elif isinstance(event, ReplyEndEvent):
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

    def _format_tool_input(self, raw_input: str) -> str:
        try:
            return json.dumps(
                json.loads(raw_input),
                ensure_ascii=False,
                indent=2,
            )
        except json.JSONDecodeError:
            return raw_input or "{}"


def configure_human_in_loop_permissions(state: AgentState) -> None:
    state.permission_context.mode = PermissionMode.DEFAULT
    state.permission_context.working_directories[str(PROJECT_ROOT)] = (
        AdditionalWorkingDirectory(
            path=str(PROJECT_ROOT),
            source="project",
        )
    )
    for tool_name in FILE_RELATED_TOOLS:
        state.permission_context.ask_rules.setdefault(tool_name, []).append(
            PermissionRule(
                tool_name=tool_name,
                rule_content=None,
                behavior=PermissionBehavior.ASK,
                source="default-human-in-loop",
            ),
        )


def build_code_agent() -> Agent:
    state = AgentState()
    configure_human_in_loop_permissions(state)

    toolkit = Toolkit(
        tools=[
            Read(),
            Write(),
            Edit(),
            Glob(),
            Grep(),
            Bash(cwd=str(PROJECT_ROOT)),
        ],
    )

    return Agent(
        name="coding_agent",
        system_prompt=(
            "You are a file-focused coding agent. Use the provided file tools "
            "to inspect, create, and edit files in the project workspace. "
            f"The project root is {PROJECT_ROOT}. When writing files, use "
            "absolute file paths. Keep outputs concise. File-related "
            "operations require human approval before execution."
        ),
        model=build_model(),
        toolkit=toolkit,
        state=state,
        react_config=ReActConfig(max_iters=8),
    )


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


async def run_agent_with_human_loop(agent: Agent, task: UserMsg) -> None:
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


async def main() -> None:
    agent = build_code_agent()
    task = UserMsg(
        name="zhangheng",
        content=os.getenv("AGENT_TASK", DEFAULT_TASK),
    )

    try:
        await run_agent_with_human_loop(agent, task)
    except HumanConfirmationUnavailable as exc:
        raise SystemExit(f"\n{exc}") from None


if __name__ == "__main__":
    asyncio.run(main())
