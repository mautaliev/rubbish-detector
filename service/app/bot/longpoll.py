"""Инициализация VK-бота и запуск Long Poll."""

import logging
import os

from vkbottle.bot import Bot

from .handlers import register_handlers

logger = logging.getLogger(__name__)


async def _diagnose_api(token: str) -> None:
    """Проверяет доступность ключевых методов VK API и логирует результат.

    Args:
        token: Токен сообщества VK.
    """
    from vkbottle.api import API
    api = API(token)
    try:
        resp = await api.request("groups.getById", {})
        groups = resp.get("response", {}).get("groups", [])
        if groups:
            group_id = groups[0]["id"]
            logger.info("VK diagnostic: groups.getById OK, group_id=%d", group_id)
        else:
            logger.warning("VK diagnostic: groups.getById returned empty groups list")
            return
    except Exception as e:
        logger.error("VK diagnostic: groups.getById FAILED — %s", e)
        return

    try:
        await api.request("groups.getLongPollServer", {"group_id": group_id})
        logger.info("VK diagnostic: groups.getLongPollServer OK")
    except Exception as e:
        logger.error("VK diagnostic: groups.getLongPollServer FAILED — %s", e)


def create_bot() -> Bot:
    """Создаёт и настраивает экземпляр VK-бота.

    Токен считывается из переменной окружения VK_TOKEN.
    Обработчики регистрируются через register_handlers().

    Returns:
        Bot: Настроенный экземпляр vkbottle Bot.
    """
    token = os.environ["VK_TOKEN"]
    bot = Bot(token=token)
    register_handlers(bot)
    return bot
