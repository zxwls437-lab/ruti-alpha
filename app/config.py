"""환경 변수 기반 설정. 값은 호출 시점에 읽어서 테스트에서 쉽게 바꿀 수 있게 한다."""
import os

from dotenv import load_dotenv

load_dotenv()


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def env_int(name: str, default: int) -> int:
    try:
        return int(env(name, str(default)))
    except ValueError:
        return default


def env_bool(name: str, default: bool) -> bool:
    raw = env(name, "true" if default else "false").lower()
    return raw in ("1", "true", "yes", "on")
