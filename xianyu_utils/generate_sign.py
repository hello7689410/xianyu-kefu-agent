import hashlib


def generate_sign(t: str, token: str, data: str) -> str:
    """生成 sign（MD5）用于 mtop 登录 token 接口。

    说明：消息体拼接格式为：`{token}&{t}&{app_key}&{data}`。
    """
    app_key = "34839810"
    msg = f"{token}&{t}&{app_key}&{data}"
    md5_hash = hashlib.md5()
    md5_hash.update(msg.encode("utf-8"))
    return md5_hash.hexdigest()

