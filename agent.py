import asyncio
import os
from pathlib import Path
from dotenv import load_dotenv

from agentscope.agent import Agent, ReActConfig
from agentscope.credential import OpenAICredential
from agentscope.message import UserMsg
from agentscope.model import OpenAIChatModel
from agentscope.permission import (
    AdditionalWorkingDirectory,
    PermissionMode,
)
from agentscope.state import AgentState
from agentscope.tool import Bash, Edit, Glob, Grep, Read, Toolkit, Write


PROJECT_ROOT = Path(__file__).resolve().parent
ENV_PATH = PROJECT_ROOT / ".env"


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
        stream=False,
        client_kwargs={"timeout": 60.0},
        parameters=OpenAIChatModel.Parameters(
            temperature=0.2,
            max_tokens=1024,
        ),
    )


def build_code_agent() -> Agent:
    state = AgentState()
    state.permission_context.mode = PermissionMode.ACCEPT_EDITS
    state.permission_context.working_directories[str(PROJECT_ROOT)] = (
        AdditionalWorkingDirectory(
            path=str(PROJECT_ROOT),
            source="project",
        )
    )

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
            "absolute file paths. Keep outputs concise."
        ),
        model=build_model(),
        toolkit=toolkit,
        state=state,
        react_config=ReActConfig(max_iters=8),
    )


async def main() -> None:
    agent = build_code_agent()
    task = UserMsg(
        name="zhangheng",
        content=(
            "请在项目根目录创建一个 README.md 文件，"
            "不要把整份 README 包在Markdown 代码块里。"
            "请使用文件工具完成写入。"
        ),
    )

    result = await agent.reply(task)
    print(result.get_text_content())

if __name__ == "__main__":
    asyncio.run(main())
