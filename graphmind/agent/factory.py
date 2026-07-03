from agentscope.agent import Agent, ContextConfig, ReActConfig
from agentscope.credential import OpenAICredential
from agentscope.model import OpenAIChatModel
from agentscope.state import AgentState
from agentscope.tool import Bash, Edit, Glob, Grep, Read, Toolkit, Write

from graphmind.agent.middleware import (
    ContextCompressionSwitch,
    ToolCallArgumentSanitizer,
)
from graphmind.agent.permissions import configure_human_in_loop_permissions
from graphmind.core.config import (
    PROJECT_ROOT,
    get_context_compression_settings,
    get_llm_settings,
)


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
        context_size=settings.context_size,
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


def build_context_config() -> ContextConfig:
    settings = get_context_compression_settings()
    return ContextConfig(
        trigger_ratio=settings.trigger_ratio,
        reserve_ratio=settings.reserve_ratio,
        tool_result_limit=settings.tool_result_limit,
    )


def build_code_agent() -> Agent:
    state = AgentState()
    configure_human_in_loop_permissions(state)
    compression_settings = get_context_compression_settings()
    state.middle_context["context_compression_enabled"] = (
        compression_settings.enabled
    )

    return Agent(
        name="coding_agent",
        system_prompt=(
            "你是一个专注于文件操作的编程智能体。"
            "请使用提供的文件工具来检查、创建和编辑项目工作区中的文件。"
            f"项目根目录为 {PROJECT_ROOT}。写入文件时，请使用绝对路径。保持输出简洁。"
            "读取文件无需人工批准，写入、编辑等修改文件的操作需经人工批准。"
            "如果任务超出你的能力范围，请直接拒绝并说明原因。"
        ),
        model=build_model(),
        toolkit=build_toolkit(),
        state=state,
        middlewares=[
            ContextCompressionSwitch(enabled=compression_settings.enabled),
            ToolCallArgumentSanitizer(),
        ],
        context_config=build_context_config(),
        react_config=ReActConfig(max_iters=15),
    )
