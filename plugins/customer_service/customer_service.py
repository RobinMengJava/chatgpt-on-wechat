# encoding:utf-8

import os
import json
from datetime import datetime

import plugins
from bridge.context import ContextType
from bridge.reply import ReplyType
from common.log import logger
from common.utils import expand_path
from plugins import *


@plugins.register(
    name="CustomerService",
    desire_priority=10,
    hidden=False,
    desc="智能客服插件：检测兜底回复并记录未解答问题",
    version="0.1",
    author="robin",
)
class CustomerService(Plugin):

    def __init__(self):
        super().__init__()
        try:
            self.config = super().load_config()
            if not self.config:
                self.config = self._load_config_template()
            self.fallback_text = self.config.get(
                "fallback_text",
                "抱歉，暂时无法回答您的问题，我会记录下来，然后好好学习。"
            )
            log_path = self.config.get("unanswered_log_path", "~/cow/unanswered_questions.log")
            self.log_path = expand_path(log_path)
            # 确保日志目录存在
            os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
            self.handlers[Event.ON_DECORATE_REPLY] = self.on_decorate_reply
            logger.info("[CustomerService] 插件初始化成功")
        except Exception as e:
            logger.error(f"[CustomerService] 初始化失败: {e}")
            raise e

    def on_decorate_reply(self, e_context: EventContext):
        if e_context["context"].type != ContextType.TEXT:
            return

        reply = e_context["reply"]
        if not reply or reply.type != ReplyType.TEXT:
            return

        content = reply.content or ""
        if self.fallback_text not in content:
            return

        # 记录未解答问题
        question = e_context["context"].content
        self._log_unanswered(question)

    def _log_unanswered(self, question: str):
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(f"[{timestamp}] {question}\n")
            logger.debug(f"[CustomerService] 记录未解答问题: {question}")
        except Exception as e:
            logger.error(f"[CustomerService] 写入日志失败: {e}")

    def get_help_text(self, **kwargs):
        return (
            "智能客服插件\n"
            f"- 兜底语: {self.fallback_text}\n"
            f"- 未解答问题日志: {self.log_path}\n"
        )

    def _load_config_template(self):
        template_path = os.path.join(self.path, "config.json.template")
        if os.path.exists(template_path):
            with open(template_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}
