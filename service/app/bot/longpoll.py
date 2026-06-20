"""Инициализация VK-бота и запуск Long Poll."""

import logging
import os

from vkbottle.bot import Bot

from .handlers import register_handlers

logger = logging.getLogger(__name__)


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
