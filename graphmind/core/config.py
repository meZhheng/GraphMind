import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = PROJECT_ROOT / ".env"
WEB_ROOT = PROJECT_ROOT / "web"
TEMPLATES_DIR = WEB_ROOT / "templates"
STATIC_DIR = WEB_ROOT / "static"

FILE_RELATED_TOOLS = ("Read", "Write", "Edit", "Glob", "Grep", "Bash")
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
    )
