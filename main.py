from __future__ import annotations

import asyncio

from WebSocket.xianLive import xianLive


def main() -> None:
    live = xianLive()
    asyncio.run(live.connect())


if __name__ == "__main__":
    main()

