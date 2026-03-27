from __future__ import annotations

from pathlib import Path


def _default_env_path() -> Path:
    # xianyu_utils/.. -> 项目根目录（.env 位于项目根目录）
    return Path(__file__).resolve().parent.parent / ".env"


def read_cookie_from_env(env_path: str | Path | None = None) -> str:
    """从 .env 中读取 XIANYU_COOKIE 的原始字符串。"""
    env_path = Path(env_path) if env_path is not None else _default_env_path()
    if not env_path.exists():
        return ""

    try:
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("XIANYU_COOKIE="):
                return line.split("=", 1)[1].strip()
    except Exception:
        return ""

    return ""

