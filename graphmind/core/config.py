import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = PROJECT_ROOT / ".env"
WEB_ROOT = PROJECT_ROOT / "web"
TEMPLATES_DIR = WEB_ROOT / "templates"
STATIC_DIR = WEB_ROOT / "static"

FILE_READ_TOOLS = ("Read", "Glob", "Grep")
FILE_MUTATION_TOOLS = ("Write", "Edit")
DEFAULT_TASK = (
    "请在项目根目录创建一个 README.md 文件，"
    "不要把整份 README 包在 Markdown 代码块里。"
    "请使用文件工具完成写入。"
)


@dataclass(frozen=True)
class LLMSettings:
    api_base: str
    model_name: str
    api_key: str = "EMPTY"
    timeout: float = 60.0
    temperature: float = 0.2
    max_tokens: int = 1024
    context_size: int = 128000


@dataclass(frozen=True)
class ContextCompressionSettings:
    enabled: bool = True
    trigger_ratio: float = 0.8
    reserve_ratio: float = 0.2
    tool_result_limit: int = 50000


def load_env(path: Path = ENV_PATH) -> None:
    load_dotenv(dotenv_path=path, override=False)


def get_llm_settings() -> LLMSettings:
    load_env()

    api_base = os.getenv("OPENAI_API_BASE")
    model_name = os.getenv("MODEL_NAME")
    if not api_base or not model_name:
        raise RuntimeError(
            "Please set OPENAI_API_BASE and MODEL_NAME in .env",
        )

    return LLMSettings(
        api_base=api_base,
        model_name=model_name,
        api_key=os.getenv("OPENAI_API_KEY", "EMPTY"),
        timeout=float(os.getenv("OPENAI_TIMEOUT", "60")),
        temperature=float(os.getenv("MODEL_TEMPERATURE", "0.2")),
        max_tokens=int(os.getenv("MODEL_MAX_TOKENS", "1024")),
        context_size=int(os.getenv("MODEL_CONTEXT_SIZE", "128000")),
    )


def get_context_compression_settings() -> ContextCompressionSettings:
    load_env()

    enabled = _env_bool("CONTEXT_COMPRESSION_ENABLED", True)
    trigger_ratio = float(os.getenv("CONTEXT_COMPRESSION_TRIGGER_RATIO", "0.8"))
    reserve_ratio = float(os.getenv("CONTEXT_COMPRESSION_RESERVE_RATIO", "0.2"))
    tool_result_limit = int(
        os.getenv("CONTEXT_COMPRESSION_TOOL_RESULT_LIMIT", "50000"),
    )

    if not 0 < trigger_ratio < 0.9:
        raise RuntimeError(
            "CONTEXT_COMPRESSION_TRIGGER_RATIO must be greater than 0 and "
            "less than 0.9",
        )
    if not 0 < reserve_ratio < trigger_ratio:
        raise RuntimeError(
            "CONTEXT_COMPRESSION_RESERVE_RATIO must be greater than 0 and "
            "less than CONTEXT_COMPRESSION_TRIGGER_RATIO",
        )
    if tool_result_limit <= 0:
        raise RuntimeError(
            "CONTEXT_COMPRESSION_TOOL_RESULT_LIMIT must be greater than 0",
        )

    return ContextCompressionSettings(
        enabled=enabled,
        trigger_ratio=trigger_ratio,
        reserve_ratio=reserve_ratio,
        tool_result_limit=tool_result_limit,
    )


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}
