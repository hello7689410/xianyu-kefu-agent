import base64
import struct
from typing import Any, Dict, List


class MessagePackDecoder:
    """MessagePack解码器的纯Python实现（用于解析 WebSocket 下行 base64 payload）"""

    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0
        self.length = len(data)

    def read_byte(self) -> int:
        if self.pos >= self.length:
            raise ValueError("Unexpected end of data")
        byte = self.data[self.pos]
        self.pos += 1
        return byte

    def read_bytes(self, count: int) -> bytes:
        if self.pos + count > self.length:
            raise ValueError("Unexpected end of data")
        result = self.data[self.pos : self.pos + count]
        self.pos += count
        return result

    def read_uint8(self) -> int:
        return self.read_byte()

    def read_uint16(self) -> int:
        return struct.unpack(">H", self.read_bytes(2))[0]

    def read_uint32(self) -> int:
        return struct.unpack(">I", self.read_bytes(4))[0]

    def read_uint64(self) -> int:
        return struct.unpack(">Q", self.read_bytes(8))[0]

    def read_int8(self) -> int:
        return struct.unpack(">b", self.read_bytes(1))[0]

    def read_int16(self) -> int:
        return struct.unpack(">h", self.read_bytes(2))[0]

    def read_int32(self) -> int:
        return struct.unpack(">i", self.read_bytes(4))[0]

    def read_int64(self) -> int:
        return struct.unpack(">q", self.read_bytes(8))[0]

    def read_float32(self) -> float:
        return struct.unpack(">f", self.read_bytes(4))[0]

    def read_float64(self) -> float:
        return struct.unpack(">d", self.read_bytes(8))[0]

    def read_string(self, length: int) -> str:
        return self.read_bytes(length).decode("utf-8")

    def decode_value(self) -> Any:
        """解码单个 MessagePack 值"""
        if self.pos >= self.length:
            raise ValueError("Unexpected end of data")

        format_byte = self.read_byte()

        # Positive fixint (0xxxxxxx)
        if format_byte <= 0x7F:
            return format_byte

        # Fixmap (1000xxxx)
        if 0x80 <= format_byte <= 0x8F:
            size = format_byte & 0x0F
            return self.decode_map(size)

        # Fixarray (1001xxxx)
        if 0x90 <= format_byte <= 0x9F:
            size = format_byte & 0x0F
            return self.decode_array(size)

        # Fixstr (101xxxxx)
        if 0xA0 <= format_byte <= 0xBF:
            size = format_byte & 0x1F
            return self.read_string(size)

        # nil
        if format_byte == 0xC0:
            return None

        # false
        if format_byte == 0xC2:
            return False

        # true
        if format_byte == 0xC3:
            return True

        # bin 8
        if format_byte == 0xC4:
            size = self.read_uint8()
            return self.read_bytes(size)

        # bin 16
        if format_byte == 0xC5:
            size = self.read_uint16()
            return self.read_bytes(size)

        # bin 32
        if format_byte == 0xC6:
            size = self.read_uint32()
            return self.read_bytes(size)

        # float 32
        if format_byte == 0xCA:
            return self.read_float32()

        # float 64
        if format_byte == 0xCB:
            return self.read_float64()

        # uint 8
        if format_byte == 0xCC:
            return self.read_uint8()

        # uint 16
        if format_byte == 0xCD:
            return self.read_uint16()

        # uint 32
        if format_byte == 0xCE:
            return self.read_uint32()

        # uint 64
        if format_byte == 0xCF:
            return self.read_uint64()

        # int 8
        if format_byte == 0xD0:
            return self.read_int8()

        # int 16
        if format_byte == 0xD1:
            return self.read_int16()

        # int 32
        if format_byte == 0xD2:
            return self.read_int32()

        # int 64
        if format_byte == 0xD3:
            return self.read_int64()

        # str 8
        if format_byte == 0xD9:
            size = self.read_uint8()
            return self.read_string(size)

        # str 16
        if format_byte == 0xDA:
            size = self.read_uint16()
            return self.read_string(size)

        # str 32
        if format_byte == 0xDB:
            size = self.read_uint32()
            return self.read_string(size)

        # array 16
        if format_byte == 0xDC:
            size = self.read_uint16()
            return self.decode_array(size)

        # array 32
        if format_byte == 0xDD:
            size = self.read_uint32()
            return self.decode_array(size)

        # map 16
        if format_byte == 0xDE:
            size = self.read_uint16()
            return self.decode_map(size)

        # map 32
        if format_byte == 0xDF:
            size = self.read_uint32()
            return self.decode_map(size)

        # Negative fixint (111xxxxx)
        if format_byte >= 0xE0:
            return format_byte - 256

        raise ValueError(f"Unknown format byte: 0x{format_byte:02x}")

    def decode_array(self, size: int) -> List[Any]:
        """解码数组"""
        result = []
        for _ in range(size):
            result.append(self.decode_value())
        return result

    def decode_map(self, size: int) -> Dict[Any, Any]:
        """解码映射"""
        result: Dict[Any, Any] = {}
        for _ in range(size):
            key = self.decode_value()
            value = self.decode_value()
            result[key] = value
        return result

    def decode(self) -> Any:
        """解码 MessagePack 数据"""
        try:
            return self.decode_value()
        except Exception:
            # 解码失败时返回原始 data 的 base64，便于你定位 payload
            return base64.b64encode(self.data).decode("utf-8")


if __name__ == "__main__":
    # 你给的 base64（聊天 payload）
    encoded_str = (
        "ggGLAYEBtTIyMTg4OTQ2NDQ5MjdAZ29vZmlzaAKzNTkxNTA5NTc5ODdAZ29vZmlzaAOxNDAzMzA1MzYxMzc4My5QTk0EAAXPAAABnSPwh48GggFlA4UBoAKiYWEDoAQBBdoAJnsiY29udGVudFR5cGUiOjEsInRleHQiOnsidGV4dCI6ImFhIn19BwIIAQkACoyrX2FwcFZlcnNpb26jMS4wqV9wbGF0Zm9ybaN3ZWKmYml6VGFn2gBBeyJzb3VyY2VJZCI6IlM6MSIsIm1lc3NhZ2VJZCI6ImYyYzQ2NDRmZWE0OTQwNWQ4MWYyNzI5ZjQ2MDNlOGU4In2sZGV0YWlsTm90aWNlojF3eVp5eXh0SnNvbtoAS3sicXVpY2tSZXBseSI6IjEiLCJtZXNzYWdlSWQiOiJmMmM0NjQ0ZmVhNDk0MDVkODFmMjcyOWY0NjAzZThlOCIsInRhZyI6InUifaRwb3J0ozQ3Nq9yZW1pbmRlckNvbnRlbnSrcmh1aWhpd2VoaWdzZXh0SnNvbtoAS3sicXVpY2tSZXBseSI6IjEiLCJtZXNzYWdlSWQiOiJmMmM0NjQ0ZmVhNDk0MDVkODFmMjcyOWY0NjAzZThlOCIsInRhZyI6InUifaRwb3J0ozQ3Nq9yZW1pbmRlckNvbnRlbnSrcmh1aWhpd2VoaWWucmVtaW5kZXJVcmzaAIlmbGVhbWFya2V0Oi8vbWVzc2FnZV9jaGF0P2l0ZW1JZD0xMDMxMDAyNzQ5NjEwJnBlZXJVc2VySWQ9MjIxODg5NDY0NDkyNyZzaWQ9NTkxNTA5NTc5ODcmbWVzc2FnZUlkPWYyYzQ2NDRmZWE0OTQwNWQ4MWYyNzI5ZjQ2MDNlOGU4JmFkdj1ub6xzZW5kZXJVc2VySWStMjIxODg5NDY0NDkyN65zZW5kZXJVc2VyVHlwZaEwq3Nlc3Npb25UeXBloTEMAQOBqG5lZWRQdXNopWZhbHNl"
    )

    raw_bytes = base64.b64decode(encoded_str)
    decoder = MessagePackDecoder(raw_bytes)
    decoded = decoder.decode()
    print(decoded)