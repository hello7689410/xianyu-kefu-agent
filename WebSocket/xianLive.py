from __future__ import annotations
import re

from loguru import logger

from xianyu_utils.cookie_env_read import read_cookie_from_env
from xianyu_utils.cookie_extract import extract_cookie
from xianyu_utils.MessagePackDecoder import MessagePackDecoder as UtilMessagePackDecoder
from typing import Dict, Any, List
import websockets
from xianyuAPI import xianyuAPI
import json
import base64
import time
import asyncio
import struct

from ContextManager import ContextManager



class xianLive:
    def __init__(self):
        # WebSocket 服务地址
        self.url = "wss://wss-goofish.dingtalk.com/"

        # 握手 headers
        self.headers = {
            "accept-encoding": "gzip, deflate, br",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
            "cache-control": "no-cache",
            "connection": "Upgrade",
            "host": "wss-goofish.dingtalk.com",
            "origin": "https://www.goofish.com",
            "pragma": "no-cache",
            "sec-websocket-extensions": "permessage-deflate; client_max_window_bits",
            "sec-websocket-key": "YX/8SVlDOFs/RsRZEqmHmA==",
            "sec-websocket-version": "13",
            "upgrade": "websocket",
            "user-agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36 Edg/146.0.0.0"
            ),
        }
        
        # 读取 cookie 字符串
        cookie_str = read_cookie_from_env()
        # 解析 cookie，为字典形式
        self.cookies = extract_cookie(cookie_str)
        # 构造myid，读取Cookie里面的unb即可
        self.myid = self.cookies.get("unb")
        #WebSocket连接，在后面会用到
        self.ws = None
        #重连标志，用于判断是否需要重连
        self.connection_restart_flag = False  # 触发重建连接

        # 心跳相关配置（可用环境变量覆盖）
        import os

        self.heartbeat_interval = int(os.getenv("HEARTBEAT_INTERVAL", "15"))  # 发送心跳间隔
        self.heartbeat_timeout = int(os.getenv("HEARTBEAT_TIMEOUT", "5"))  # 心跳超时
        self.last_heartbeat_time = 0.0
        self.last_heartbeat_response = 0.0
        self.last_heartbeat_mid = None
        self.heartbeat_task = None

        # Token刷新（到点触发重连并重新 /reg）
        self.token_refresh_interval = int(os.getenv("TOKEN_REFRESH_INTERVAL", "3600"))
        self.token_retry_interval = int(os.getenv("TOKEN_RETRY_INTERVAL", "300"))
        self.last_token_refresh_time = 0.0
        self.token_refresh_task = None

        # 用于持久化聊天上下文（SQLite）
        self.context_manager = ContextManager()

    async def send_ack(self, message_data: dict):
        """
        根据服务端下行消息中的 headers 构造 ACK，并回发给 WS 服务端。
        """
        headers = message_data.get("headers", {}) if isinstance(message_data, dict) else {}
        mid = headers.get("mid")
        sid = headers.get("sid", "")
        if not mid:
            return

        ack = {
            "code": 200,
            "headers": {
                "mid": mid,
                "sid": sid,
            },
        }
        #看是否还有其他的头
        for key in ("app-key", "ua", "dt"):
            if key in headers:
                ack["headers"][key] = headers[key]
        #发送ack
        await self.ws.send(json.dumps(ack, ensure_ascii=False))


    async def send_msg(self, cid: str, text: str, receiver_ids: list[str], conversation_type: int = 1):
        """
        发送消息，参数为聊天ID，消息内容，接收者ID，会话类型
        """
        #先确定WebSocket连接是否存在
        if not self.ws:
            raise RuntimeError("WebSocket未连接，无法发送消息")

        #将ID加上@goofish
        def normalize_uid(uid: str) -> str:
            uid = str(uid)
            return uid if "@goofish" in uid else f"{uid}@goofish"

        #相互联系的人ID
        actual_receivers = [normalize_uid(uid) for uid in receiver_ids]

        #生成消息ID
        msg_uuid = f"-{int(time.time() * 1000)}{str(int(time.time() * 1000000))[-2:]}"
        #生成消息内容
        inner_content = {"contentType": 1, "text": {"text": text}}
        #生成消息内容base64
        custom_data_b64 =str(base64.b64encode(json.dumps(inner_content).encode('utf-8')), 'utf-8')

        payload = {
            "lwp": "/r/MessageSend/sendByReceiverScope",
            "headers": {"mid": self.generate_mid()},
            "body": [
                {
                    "uuid": msg_uuid,
                    "cid": cid,
                    "conversationType": conversation_type,
                    "content": {
                        "contentType": 101,
                        "custom": {"type": 1, "data": custom_data_b64},
                    },
                    "ctx": {"appVersion": "1.0", "platform": "web"},
                    "extension": {"extJson": "{}"},
                    "msgReadStatusSetting": 1,
                    "mtags": {},
                    "redPointPolicy": 0,
                },
                {"actualReceivers": actual_receivers},
            ],
        }

        await self.ws.send(json.dumps(payload, ensure_ascii=False))
        logger.info(f"[WS] 已发送消息: cid={cid}, receivers={actual_receivers}, text={text}")
        return payload



    async def send_reg_with_access_token(self):
        # 获取 accessToken
        api = xianyuAPI()
        res_json = api.get_accessKEy()
        if not res_json or "data" not in res_json or "accessToken" not in res_json["data"]:
            print("无法获取 accessToken，ws 注册包无法发送")
            return
        access_token = res_json["data"]["accessToken"]

        # 动态生成 mid
        current_mid = self.generate_mid()

        #构造注册包，通过抓包获取的
        reg_package = {
            "lwp": "/reg",
            "headers": {
                "cache-header": "app-key token ua wv",
                "app-key": "444e9908a51d1cb236a27862abc769c9",
                "did": "2BF53FAD-179A-46E6-960D-B1098777BD31-2218894644927",
                "dt": "j",
                "mid": current_mid,
                "sync": "0,0;0;0;",
                "token": access_token,
                "ua": self.headers.get("User-Agent") or self.headers.get("user-agent"),
                "wv": "im:3,au:3,sy:6",
            },
        }
        #发送注册包
        await self.ws.send(json.dumps(reg_package, ensure_ascii=False))
        print(f"[WS] 已发送注册包, mid: {current_mid}")

        # 等待服务器返回注册成功的 ACK（简单延迟）
        await asyncio.sleep(0.5)

        
        #构造ackDiff(同步差量请求)，通过抓包获取的
        diff_mid = self.generate_mid()
        ack_diff_msg =  {"lwp": "/r/SyncStatus/ackDiff", "headers": {"mid": "5701741704675979 0"}, "body": [
            {"pipeline": "sync", "tooLong2Tag": "PNM,1", "channel": "sync", "topic": "sync", "highPts": 0,
             "pts": int(time.time() * 1000) * 1000, "seq": 0, "timestamp": int(time.time() * 1000)}]}
        #开始发送ackDiff
        ack_diff_msg["headers"]["mid"] = diff_mid
        await self.ws.send(json.dumps(ack_diff_msg, ensure_ascii=False))
        print("[WS] 已发送 ackDiff, 开启订阅推送")

        # 记录“最近一次完成 reg/ackDiff 的时间”
        self.last_token_refresh_time = time.time()

    async def send_heartbeat(self, ws):
        """发送心跳包，并记录 mid/时间"""
        heartbeat_mid = self.generate_mid()
        heartbeat_msg = {"lwp": "/!", "headers": {"mid": heartbeat_mid}}
        await ws.send(json.dumps(heartbeat_msg, ensure_ascii=False))
        self.last_heartbeat_mid = heartbeat_mid
        self.last_heartbeat_time = time.time()
        logger.debug(f"[WS] 已发送心跳, mid={heartbeat_mid}")
        return heartbeat_mid
    
    #心跳循环，用于周期发送心跳,保证连接的稳定性
    async def heartbeat_loop(self, ws):
        """周期发送心跳；若超时则触发重连"""
        while True:
            try:
                now = time.time()
                if now - self.last_heartbeat_time >= self.heartbeat_interval:
                    await self.send_heartbeat(ws)

                # 未收到响应则判定为连接异常
                if self.last_heartbeat_mid and (now - self.last_heartbeat_response) > (
                    self.heartbeat_interval + self.heartbeat_timeout
                ):
                    logger.warning("[WS] 心跳响应超时，触发重连")
                    self.connection_restart_flag = True
                    await ws.close()
                    return

                await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"[WS] 心跳循环出错: {e}")
                self.connection_restart_flag = True
                try:
                    await ws.close()
                except Exception:
                    pass
                return

    #Token刷新循环，用于定时刷新token
    async def token_refresh_loop(self):
        """到点刷新 token：触发重连（重连时会重新 /reg + ackDiff）"""
        while True:
            try:
                now = time.time()
                if self.last_token_refresh_time and (now - self.last_token_refresh_time) >= self.token_refresh_interval:
                    logger.info("[WS] Token刷新到期，触发重连并重新注册")
                    self.connection_restart_flag = True
                    if self.ws:
                        await self.ws.close()
                    return

                await asyncio.sleep(10)
            except Exception as e:
                logger.error(f"[WS] Token刷新循环出错: {e}")
                await asyncio.sleep(self.token_retry_interval)

    #判断是否能够收到心跳
    def handle_heartbeat_response(self, parsed: dict) -> bool:
        """
        处理心跳响应。
        命中当前心跳 mid 时，更新时间并返回 True（表示该消息已处理）。
        """
        if (
            isinstance(parsed, dict)
            and parsed.get("code") == 200
            and isinstance(parsed.get("headers"), dict)
            and self.last_heartbeat_mid
            and parsed["headers"].get("mid") == self.last_heartbeat_mid
        ):
            self.last_heartbeat_response = time.time()
            logger.debug("[WS] 收到心跳响应")
            return True
        return False

    #提取出真正的聊天相关的信息
    def extract_chat_base64_list(self, parsed: dict, object_type: int = 40000) -> list[str]:
        """从 syncPushPackage.data 中提取指定 objectType 的 base64 聊天数据。"""
        sync_items = parsed.get("body", {}).get("syncPushPackage", {}).get("data", [])
        if isinstance(sync_items, dict):
            sync_items = [sync_items]
        elif not isinstance(sync_items, list):
            sync_items = []

        chat_data_list = []
        for item in sync_items:
            if (
                isinstance(item, dict)
                and item.get("objectType") == object_type
                and isinstance(item.get("data"), str)
            ):
                chat_data_list.append(item["data"])
        return chat_data_list

    #message id生成器
    def generate_mid(self):
        # 生成类似 1711000000000000 0 的结构
        return f"{int(time.time() * 1000000)} 0"

    #处理消息，用于处理收到的消息,
    async def handle_message(self, parsed: dict) -> None:
        """
        1.发送ack
        2.提取出聊天信息，即 base64 编码的结果
        3.解码聊天信息，提取出发送方信息，聊天ID，发送者ID，昵称，消息内容
        4.调用 get_item_info 来获取商品信息
        5.保存入站消息（根据发送方区分 role：真人->user / 自己->assistant）
        6.判断是否是顾客发送的信息，是顾客发送的信息才要启动 AI 进行回复
        7.调用 chatbot 来生成回复，传入用户信息和商品信息
        8.通过 send_msg 把回复发回闲鱼聊天
        9.同步保存“自己（AI）发送”的消息，避免只靠服务端回显
        """
        # 收到带 mid 的消息后，及时 ACK
        await self.send_ack(parsed)

        # 提取出聊天信息，即 base64 编码的结果
        chat_data_list = self.extract_chat_base64_list(parsed, object_type=40000)
        if not chat_data_list:
            return

        #遍历聊天信息
        for idx, item in enumerate(chat_data_list, 1):
            try:
                decoded_msg = UtilMessagePackDecoder(
                    # 将base64编码的聊天信息转换为bytes，即将base64数据进行纯化
                    base64.b64decode(item.encode("utf-8"))
                ).decode()

                # 提取出发送方信息
                sender_info = decoded_msg.get(1, {})
                details = sender_info.get(10, {})
                cid = sender_info.get(2)  # 聊天ID
                sender_id = details.get("senderUserId")  # 发送者ID
                sender_nickname = details.get("reminderTitle")  # 昵称
                sender_content = details.get("reminderContent")  # 消息内容
                logger.info(
                    f"消息发送方ID: {sender_id}, 昵称: {sender_nickname}, 消息内容: {sender_content}, cid: {cid}"
                )

                # 调用 get_item_info 来获取商品信息
                item_id_value = None
                product_info = None
                item_id = details.get("reminderUrl", "") or ""
                if item_id:
                    import urllib.parse

                    parsed_url = urllib.parse.urlparse(item_id)
                    query_params = urllib.parse.parse_qs(parsed_url.query)
                    item_id_value = query_params.get("itemId", [None])[0]

                #调用get_item_detial来获取商品信息
                if item_id_value:
                    product_info = None
                    try:
                        api = xianyuAPI()
                        product_info = api.get_item_detail(item_id_value)

                        # 保存商品信息到 SQLite（会 upsert，不会重复插入）
                        try:
                            if isinstance(product_info, dict):
                                price = (
                                    product_info.get("sold_price")
                                    or product_info.get("promotionPrice")
                                    or product_info.get("original_price")
                                )
                                description = (
                                    product_info.get("product_info")
                                    or product_info.get("desc")
                                    or ""
                                )
                            else:
                                price = None
                                description = str(product_info or "")
                            
                            #将信息保存到SQLite中
                            if item_id_value and description:
                                self.context_manager.save_item_info(
                                    item_id=str(item_id_value),
                                    price=price,
                                    description=str(description),
                                )
                        except Exception as e:
                            logger.error(f"[Context] 保存商品信息失败: {e}")
                    except Exception as e:
                        logger.error(f"获取商品信息失败: {e}")

                # 保存入站消息（根据发送方区分 role：真人->user / 自己->assistant）
                if sender_id and item_id_value and sender_content:
                    role = "assistant" if str(sender_id) == str(self.myid) else "user"
                    try:
                        self.context_manager.save_chat_message(
                            sender_id=str(sender_id),
                            item_id=str(item_id_value),
                            content=str(sender_content),
                            role=role,
                            timestamp=int(time.time() * 1000),
                        )
                    except Exception as e:
                        logger.error(f"[Context] 保存聊天消息失败: {e}")

                reply_text = ""

                # 判断是否是顾客发送的信息，是顾客发送的信息才要启动 AI 进行回复
                if sender_id and cid and sender_id != self.myid:
                    # 调用 chatbot 来生成回复，传入用户信息和商品信息
                    try:
                        from agents.xianyu_agent import xianyuChatbot
                    except ImportError:
                        print("调用xianyuAgent失败")
                        xianyuChatbot = None

                    chatbot = xianyuChatbot() if xianyuChatbot else None

                    if chatbot and sender_content:
                        #读取SQLlite数据库的信息，构造product_info（需要发给AI）
                        cached_item = (
                            self.context_manager.get_item_info(item_id_value)
                            if item_id_value
                            else None
                        )
                        #将信息转换为字符串形式
                        if isinstance(cached_item, dict):
                            product_info_str = (
                                f"商品ID：{cached_item.get('id')}\n"
                                f"价格：{cached_item.get('price')}\n"
                                f"{cached_item.get('description') or ''}"
                            )
                        else:
                            product_info_str = str(product_info or "")

                        #构造chat_id，即键值
                        chat_id = (
                            f"{sender_id}_{item_id_value}" if sender_id and item_id_value else ""
                        )
                        #读取聊天历史
                        history_rows = (
                            self.context_manager.get_chat_messages(chat_id=chat_id, limit=50)
                            if chat_id
                            else []
                        )
                        chat_history_lines = [
                            f'{row.get("role")}: {row.get("content")}'
                            for row in history_rows
                            if row.get("role") is not None and row.get("content") is not None
                        ]
                        chat_history_str = "\n".join(chat_history_lines)

                        #传给AI进行回复
                        try:
                            reply_text = chatbot.reply(
                                product_info=product_info_str,
                                last_user_message=sender_content,
                                chat_history=chat_history_str,
                            )
                            print("reply_text", reply_text)
                        except Exception as e:
                            logger.error(f"调用chatbot.reply失败: {e}")

                    #将回复发回闲鱼聊天
                    await self.send_msg(
                        cid=cid,
                        text=reply_text,
                        receiver_ids=[sender_id, self.myid],
                    )

                    #保存聊天历史
                    if item_id_value and reply_text:
                        try:
                            self.context_manager.save_chat_message(
                                # 为了让同一会话的历史能被取到：AI回复也用“对方sender_id”作为 chat_id 的 sender 组成部分
                                sender_id=str(sender_id),
                                item_id=str(item_id_value),
                                content=str(reply_text),
                                role="assistant",
                                timestamp=int(time.time() * 1000),
                            )
                        except Exception as e:
                            logger.error(f"[Context] 保存AI回复失败: {e}")
            except Exception as e:
                logger.error(f"[WS] 处理消息时发生错误（idx={idx}）: {e}")

    async def connect(self):
        """
        连接 WebSocket 服务。
        """
        while True:
            self.connection_restart_flag = False    #重连标志，用于判断是否需要重连
            self.last_heartbeat_mid = None           #心跳mid，用于判断是否收到心跳
            self.last_heartbeat_response = time.time() #心跳响应时间，用于判断是否收到心跳

            heartbeat_task = None    #心跳任务
            token_refresh_task = None    #Token刷新任务

            try:
                # 建立WebSocket连接
                async with websockets.connect(self.url, extra_headers=self.headers) as ws:
                    self.ws = ws
                    print("[WS] 连接成功")

                    await self.send_reg_with_access_token()    #发送注册包
                    logger.info("连接注册完成，开始监听信息")

                    # 初始化心跳时间
                    self.last_heartbeat_time = time.time()
                    self.last_heartbeat_response = time.time()

                    # 启动后台任务
                    heartbeat_task = asyncio.create_task(self.heartbeat_loop(ws))
                    token_refresh_task = asyncio.create_task(self.token_refresh_loop())

                    #监听信息
                    async for message in ws:
                        if self.connection_restart_flag:
                            break
                        #解析消息，先开始提取data，然后再继续编码，然后再将编码后的内容提取出要用的信息
                        try:
                            if isinstance(message, (bytes, bytearray)):
                                message = message.decode("utf-8", errors="ignore")
                         
                            parsed = json.loads(message)

                            #心跳
                            if self.handle_heartbeat_response(parsed):
                                continue

                            # 处理 ACK/解码/入库/AI 回复等逻辑（已迁移到 handle_message）
                            await self.handle_message(parsed)
                            continue
                            
                            #（已迁移到 handle_message）
                        except Exception as e:
                            logger.error(f"[WS] 处理消息时发生错误: {e}")

            except websockets.exceptions.ConnectionClosed:
                logger.warning("[WS] WebSocket连接已关闭")
            except Exception as e:
                logger.error(f"[WS] 连接发生错误: {e}")
            finally:
                # 清理任务
                for task in (heartbeat_task, token_refresh_task):
                    if task:
                        task.cancel()
                        try:
                            await task
                        except Exception:
                            pass

            # 主动重连：立即继续；否则等一段时间再连
            if self.connection_restart_flag:
                logger.info("[WS] 触发重连，立即重新建立连接...")
                await asyncio.sleep(1)
                continue

            logger.info("[WS] 等待5秒后重连...")
            await asyncio.sleep(5)
                    
if __name__ == "__main__":
    import asyncio

    # INSERT_YOUR_CODE
    live = xianLive()
    asyncio.run(live.connect())
