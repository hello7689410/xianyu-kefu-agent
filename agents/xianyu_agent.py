from __future__ import annotations

import json
import os
import re
from pathlib import Path
from dataclasses import dataclass
from typing import Any, Optional

from dotenv import load_dotenv
from loguru import logger
from openai import OpenAI


#构造llm，即OpenAI的客户端
class LLM:
    def __init__(self, client: OpenAI, model: str):
        self._client = client
        self._model = model


@dataclass
class BaseAgent:
    def __init__(self, llm: LLM, prompt: str):
        self.llm = llm
        self.prompt = prompt
        # 默认温度：通用回答更“稳”，价格/技术可在子类中覆盖
        self.temperature: float = 0.7
    
    #构造消息
    def build_message(
        self,
        system_message: str,
        user_message: str,
        item_info: str,
        context_messages: str | list[str],
    ):
        if isinstance(context_messages, list):
            context_text = "\n".join(context_messages)
        else:
            context_text = context_messages or ""

        messages = [
            {"role": "system", "content": system_message},
            {"role": "assistant", "content": item_info},
            {"role": "user", "content": context_text},
            {"role": "user", "content": user_message}
        ]
        return messages

    #调用llm
    def call_llm(self, message: list[dict], temperature: float | None = None) -> str:
        """
        调用 LLM，传入消息 message (一个消息字典列表) 和 temperature，返回生成的文本结果
        """
        if temperature is None:
            temperature = self.temperature
        response = self.llm._client.chat.completions.create(
            model=self.llm._model,
            messages=message,
            temperature=temperature,
        )
        return response.choices[0].message.content.strip()

    #运行agent
    def run(
        self,
        user_message: str,
        item_info: str = "",
        context_messages: str | list[str] = "",
        temperature: float | None = None,
    ) -> str:
        messages = self.build_message(self.prompt, user_message, item_info, context_messages)
        return self.call_llm(messages, temperature=temperature)

class PriceAgent(BaseAgent):
    def __init__(self, llm: LLM, prompt: str):
        super().__init__(llm, prompt)
        self.temperature = 0.5


class TechAgent(BaseAgent):
    def __init__(self, llm: LLM, prompt: str):
        super().__init__(llm, prompt)
        self.temperature = 0.5


class DefaultAgent(BaseAgent):
    def __init__(self, llm: LLM, prompt: str):
        super().__init__(llm, prompt)
        self.temperature = 0.7


class ClassifierAgent(BaseAgent):
    """
    将用户问题分类到：
    - price：估价/价格相关
    - tech：技术/参数/原理/配置相关
    - default：其他
    """

    def classify(self, user_text: str) -> str:
        text = (user_text or "").strip()

        # 1) 先用规则直接判断：优先处理“询问价格/金钱”
        money_patterns = [
            r"多少钱",
            r"多少\s*钱",
            r"(价格|报价|出价|预算|估价|成交价)\s*[^\d]{0,8}\d",
            r"¥\s*\d+(\.\d+)?",
            r"\d+(\.\d+)?\s*(元|块|人民币)"
        ]
        if any(re.search(p, text) for p in money_patterns):
            return "price"

        # 2) 再判断“询问配置/技术/产品本身相关”
        tech_keywords = [
            "参数", "配置", "型号", "规格", "尺寸", "重量", "电压", "功率",
            "接口", "兼容", "支持", "不支持", "适配", "使用", "怎么用", "说明",
            "原理", "原装", "工艺", "保养", "安装", "驱动", "电机", "电源",
            "螺丝", "线材", "接头", "端子", "螺钉", "固件", "软件", "驱动器",
            "能不能用", "可不可以", "会不会"
        ]
        if any(k in text for k in tech_keywords):
            return "tech"

        # 3) 规则不够确定时，才交给 LLM 分类（兜底）
        raw = self.run(user_text, temperature=0.0)
        

        try:
            obj = json.loads(raw)
            t = str(obj.get("type", "")).strip()
        except Exception:
            t = ""

        if t in ("price", "tech", "default"):
            return t

        return "default"


class xianyuChatbot:
    def __init__(self):
        # 1) 初始化 LLM
        self.llm = self.load_llm()

        # 2) 初始化提示词，从 prompt 目录下读取 4 个 prompt 文件
        project_root = Path(__file__).resolve().parent.parent
        prompt_dir = project_root / "prompt"
        with open(prompt_dir / "classifer_prompt.md", "r", encoding="utf-8") as f:
            classifier_prompt = f.read()
        with open(prompt_dir / "defalut_prompt.md", "r", encoding="utf-8") as f:
            default_prompt = f.read()
        with open(prompt_dir / "price_prompt.md", "r", encoding="utf-8") as f:
            price_prompt = f.read()
        with open(prompt_dir / "tech_prompt.md", "r", encoding="utf-8") as f:
            tech_prompt = f.read()
        self.prompts = {
            "classifier": classifier_prompt,
            "default": default_prompt,
            "price": price_prompt,
            "tech": tech_prompt,
        }

        # 3) 初始化 4 个 Agent
        self.priceAgent = PriceAgent(self.llm, self.prompts["price"])
        self.techAgent = TechAgent(self.llm, self.prompts["tech"])
        self.DefaultAgent = DefaultAgent(self.llm, self.prompts["default"])
        self.classifierAgent = ClassifierAgent(self.llm, self.prompts["classifier"])
    def reply(self, product_info: str, last_user_message: str, chat_history: list[str]) -> str:
        """
        通过 classifierAgent 判断用户意图，选择合适的 Agent（priceAgent, techAgent, DefaultAgent）来回复。

        :param product_info: 商品信息
        :param last_user_message: 用户的上一条信息
        :param chat_history: 完整的对话历史（list[str]）
        :return: Agent 回复内容
        """
        # 意图分类只基于用户最后一句话
        task_type = self.classifierAgent.classify(last_user_message)
        print(f"意图分类结果：{task_type}")
        if task_type == "price":
            # 议价对话
            reply = self.priceAgent.run(last_user_message, product_info, chat_history)
        elif task_type == "tech":
            # 技术类问题
            reply = self.techAgent.run(last_user_message, product_info, chat_history)
        else:
            # 默认对话
            reply = self.DefaultAgent.run(last_user_message, product_info, chat_history)
        return reply
    #加载模型llm，从.env文件中读取模型配置
    def load_llm(self) -> LLM:

        """
        从 .env 读取模型配置并初始化 LLM：
        - MODEL_NAME
        - MODEL_API_KEY
        - MODEL_BASE_URL
        """
        load_dotenv()
        model_name = os.getenv("MODEL_NAME", "").strip()
        model_api_key = os.getenv("MODEL_API_KEY", "").strip()
        model_base_url = os.getenv("MODEL_BASE_URL", "").strip()

        if not model_name:
            raise ValueError("MODEL_NAME 未配置，请在 .env 中设置。")
        if not model_api_key:
            raise ValueError("MODEL_API_KEY 未配置，请在 .env 中设置。")

        client_kwargs: dict[str, str] = {"api_key": model_api_key}
        if model_base_url:
            client_kwargs["base_url"] = model_base_url

        client = OpenAI(**client_kwargs)
        logger.info(f"LLM loaded: model={model_name}, base_url={model_base_url or 'default'}")
        return LLM(client=client, model=model_name)
# 调用 price_agent, tech_agent, default_agent 来测试功能怎么样
if __name__ == "__main__":
    from xianyuAPI import xianyuAPI

    # 通过闲鱼 API 拉取商品详情，动态构造 product_info
    item_id = "779900965184"
    item_api = xianyuAPI()
    item_detail = item_api.get_item_detail(item_id)
    if not item_detail:
        raise RuntimeError("获取商品详情失败，无法启动对话。")

    # 优先使用后端已经整理好的 product_info 文本；没有则兜底转 JSON 字符串
    product_info = item_detail.get("product_info")
    if not product_info:
        product_info = json.dumps(item_detail, ensure_ascii=False)

    # 历史对话初始化
    chat_history = []

    # 初始化 XianyuChatbot
    bot = xianyuChatbot()

    print("欢迎体验闲鱼卖家Agent，输入内容测试（输入exit退出）：")
    while True:
        # 每一轮用户输入都会作为 last_user_message
        last_user_message = input("你：").strip()
        if last_user_message.lower() in ("exit", "quit"):
            print("已退出。")
            break
        if not last_user_message:
            continue

        reply = bot.reply(product_info, last_user_message, chat_history)
        print("AI回复：", reply)
        chat_history.append(f"用户：{last_user_message}")
        chat_history.append(f"AI：{reply}")