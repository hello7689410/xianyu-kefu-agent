import sqlite3
from pathlib import Path
from typing import Optional, Any, List, Dict

#内容管理器
class ContextManager:
    """
    使用 SQLite 存储商品信息：
    - id: 商品ID（主键）
    - price: 商品价格（REAL）
    - description: 商品描述（TEXT）
    """
    #初始化
    def __init__(self, db_path: Optional[str] = None):
        project_root = Path(__file__).resolve().parent
        self.db_path = Path(db_path) if db_path else project_root / "context.db"
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_db()
    #初始化数据库
    def _init_db(self) -> None:
        cur = self.conn.cursor()
        #创建商品信息表，包括商品ID、价格、描述
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS items (
                id TEXT PRIMARY KEY,
                price REAL,
                description TEXT
            )
            """
        )

        #创建聊天数据库：只记录 sender_id、商品相关信息与消息内容
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender_id TEXT,
                item_id TEXT,
                timestamp INTEGER,
                content TEXT,
                chat_id TEXT,
                role TEXT
            )
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_messages_chat_id_ts
            ON messages(chat_id, timestamp)
            """
        )
        self.conn.commit()

    @staticmethod
    #解析价格
    def _parse_price(value: Any) -> Optional[float]:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        try:
            s = str(value).strip().replace("¥", "").replace(",", "")
            import re

            m = re.search(r"[-+]?\\d*\\.?\\d+", s)
            return float(m.group(0)) if m else None
        except Exception:
            return None

    #保存商品信息，包括商品ID、价格、描述
    def save_item_info(self, item_id: str, price: Any, description: str) -> None:
        """upsert 商品信息：没有则插入，有则更新。"""
        price_val = self._parse_price(price)
        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT INTO items (id, price, description)
            VALUES (?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                price = excluded.price,
                description = excluded.description
            """,
            (str(item_id), price_val, description),
        )
        self.conn.commit()

    def get_item_info(self, item_id: str) -> Optional[dict]:
        """读取商品信息；不存在返回 None。"""
        cur = self.conn.cursor()
        cur.execute(
            "SELECT id, price, description FROM items WHERE id = ?",
            (str(item_id),),
        )
        row = cur.fetchone()
        if not row:
            return None
        return {"id": row["id"], "price": row["price"], "description": row["description"]}

    #保存聊天消息，包括发送者ID，商品ID、时间戳、内容、聊天ID、角色
    def save_chat_message(
        self,
        sender_id: str,
        item_id: str,
        content: str,
        role: str,
        timestamp: Optional[int] = None,
    ) -> None:
        """
        保存一条聊天消息。

        字段说明：
        - sender_id: 发送者ID
        - item_id: 商品ID
        - timestamp: 时间戳（建议使用毫秒；默认当前时间）
        - content: 消息内容
        - chat_id: = sender_id + "_" + item_id
        - role: '真人' 或 'AI'
        """
        import time as _time

        ts = int(timestamp) if timestamp is not None else int(_time.time() * 1000)
        chat_id = f"{sender_id}_{item_id}"

        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT INTO messages (sender_id, item_id, timestamp, content, chat_id, role)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (str(sender_id), str(item_id), ts, content, chat_id, role),
        )
        self.conn.commit()

    #获取聊天消息：只返回与 sender_id/商品相关的内容
    def get_chat_messages(self, chat_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """按 chat_id 获取聊天历史（默认取最近 50 条）。"""
        cur = self.conn.cursor()
        cur.execute(
            """
            SELECT sender_id, item_id, timestamp, content, chat_id, role
            FROM messages
            WHERE chat_id = ?
            ORDER BY timestamp ASC
            LIMIT ?
            """,
            (str(chat_id), int(limit)),
        )
        rows = cur.fetchall()
        return [
            {
                "sender_id": row["sender_id"],
                "item_id": row["item_id"],
                "timestamp": row["timestamp"],
                "content": row["content"],
                "chat_id": row["chat_id"],
                "role": row["role"],
            }
            for row in rows
        ]

    def close(self) -> None:
        try:
            self.conn.close()
        except Exception:
            pass
