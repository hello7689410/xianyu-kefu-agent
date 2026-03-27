from __future__ import annotations

from pathlib import Path


def _default_env_path() -> Path:
    # xianyu_utils/.. -> 项目根目录（.env 位于项目根目录）
    return Path(__file__).resolve().parent.parent / ".env"


def write_cookie_to_env(cookie_str: str, env_path: str | Path | None = None) -> None:
    """写入/覆盖 .env 中的 XIANYU_COOKIE；若不存在则追加到文件末尾。"""
    env_path = Path(env_path) if env_path is not None else _default_env_path()
    cookie_str = (cookie_str or "").strip()
    if not cookie_str:
        raise ValueError("cookie_str 不能为空")

    lines: list[str] = []
    found = False

    if env_path.exists():
        try:
            lines = env_path.read_text(encoding="utf-8").splitlines(keepends=True)
        except Exception:
            lines = []

    for i, line in enumerate(lines):
        if line.startswith("XIANYU_COOKIE="):
            lines[i] = f"XIANYU_COOKIE={cookie_str}\n"
            found = True
            break

    if not found:
        if lines and not lines[-1].endswith("\n"):
            lines[-1] = lines[-1] + "\n"
        lines.append(f"XIANYU_COOKIE={cookie_str}\n")

    env_path.write_text("".join(lines), encoding="utf-8")

