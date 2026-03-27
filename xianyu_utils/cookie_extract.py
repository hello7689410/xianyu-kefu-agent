from __future__ import annotations


def extract_cookie(cookie_str: str) -> dict[str, str]:
    """
    解析 Cookie 字符串（name=value; name2=value2; ...）为 requests 可用的 dict。
    兼容 .env 写成 XIANYU_COOKIE="a=b; c=d" 或 'a=b; c=d'。
    """
    cookie_str = (cookie_str or "").strip()
    if not cookie_str:
        return {}

    # 兼容 .env 里写成外层引号的情况
    if (
        len(cookie_str) >= 2
        and cookie_str[0] == cookie_str[-1]
        and cookie_str[0] in ("'", '"')
    ):
        cookie_str = cookie_str[1:-1].strip()

    cookies: dict[str, str] = {}
    for part in cookie_str.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        name, value = part.split("=", 1)
        name = name.strip()
        value = value.strip()
        if not name:
            continue
        cookies[name] = value
    return cookies

