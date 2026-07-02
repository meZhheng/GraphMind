import asyncio
import os

from agentscope.message import UserMsg

from graphmind.agent.cli import HumanConfirmationUnavailable, run_agent_cli
from graphmind.agent.factory import build_code_agent
from graphmind.core.config import DEFAULT_TASK


async def main() -> None:
    agent = build_code_agent()
    task = UserMsg(
        name="zhangheng",
        content=os.getenv("AGENT_TASK", DEFAULT_TASK),
    )

    try:
        await run_agent_cli(agent, task)
    except HumanConfirmationUnavailable as exc:
        raise SystemExit(f"\n{exc}") from None


if __name__ == "__main__":
    asyncio.run(main())
