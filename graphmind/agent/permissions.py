from agentscope.permission import (
    AdditionalWorkingDirectory,
    PermissionBehavior,
    PermissionMode,
    PermissionRule,
)
from agentscope.state import AgentState

from graphmind.core.config import (
    FILE_MUTATION_TOOLS,
    FILE_READ_TOOLS,
    PROJECT_ROOT,
)


def configure_human_in_loop_permissions(state: AgentState) -> None:
    state.permission_context.mode = PermissionMode.DEFAULT
    state.permission_context.working_directories[str(PROJECT_ROOT)] = (
        AdditionalWorkingDirectory(
            path=str(PROJECT_ROOT),
            source="project",
        )
    )

    for tool_name in FILE_READ_TOOLS:
        state.permission_context.allow_rules.setdefault(tool_name, []).append(
            PermissionRule(
                tool_name=tool_name,
                rule_content=None,
                behavior=PermissionBehavior.ALLOW,
                source="default-read-access",
            ),
        )

    for tool_name in FILE_MUTATION_TOOLS:
        state.permission_context.ask_rules.setdefault(tool_name, []).append(
            PermissionRule(
                tool_name=tool_name,
                rule_content=None,
                behavior=PermissionBehavior.ASK,
                source="default-human-in-loop",
            ),
        )
