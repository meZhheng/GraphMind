from agentscope.agent import Agent, ReActConfig
from agentscope.credential import OpenAICredential
from agentscope.model import OpenAIChatModel
from agentscope.state import AgentState
from agentscope.tool import Bash, Edit, Glob, Grep, Read, Toolkit, Write

from graphmind.agent.permissions import configure_human_in_loop_permissions
from graphmind.core.config import PROJECT_ROOT, get_llm_settings


def build_model() -> OpenAIChatModel:
    settings = get_llm_settings()
    credential = OpenAICredential(
        api_key=settings.api_key,
        base_url=settings.api_base,
    )
    return OpenAIChatModel(
        credential=credential,
        model=settings.model_name,
        stream=True,
        client_kwargs={"timeout": settings.timeout},
        parameters=OpenAIChatModel.Parameters(
            temperature=settings.temperature,
            max_tokens=settings.max_tokens,
        ),
    )


def build_toolkit() -> Toolkit:
    return Toolkit(
        tools=[
            Read(),
            Write(),
            Edit(),
            Glob(),
            Grep(),
            Bash(cwd=str(PROJECT_ROOT)),
        ],
    )


def build_code_agent() -> Agent:
    state = AgentState()
    configure_human_in_loop_permissions(state)

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
        toolkit=build_toolkit(),
        state=state,
        react_config=ReActConfig(max_iters=8),
    )
