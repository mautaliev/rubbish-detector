"""Генераторы VK-клавиатур для всех сценариев взаимодействия."""

import json

from vkbottle import Keyboard, KeyboardButtonColor, Text


def role_keyboard() -> str:
    """Клавиатура выбора роли для незарегистрированного пользователя.

    Returns:
        str: JSON-строка клавиатуры VK.
    """
    kb = Keyboard(one_time=True)
    kb.add(Text("Упр. организация"), color=KeyboardButtonColor.PRIMARY)
    kb.add(Text("Сотрудник по уборке"), color=KeyboardButtonColor.PRIMARY)
    return kb.get_json()


def consent_keyboard() -> str:
    """Клавиатура согласия для дворника при регистрации.

    Returns:
        str: JSON-строка клавиатуры VK.
    """
    kb = Keyboard(one_time=True)
    kb.add(Text("Принимаю"), color=KeyboardButtonColor.POSITIVE)
    kb.add(Text("Отмена"), color=KeyboardButtonColor.NEGATIVE)
    return kb.get_json()


def admin_keyboard() -> str:
    """Главная клавиатура панели администратора.

    Returns:
        str: JSON-строка клавиатуры VK.
    """
    kb = Keyboard(one_time=True)
    kb.add(Text("Заявки на регистрацию"), color=KeyboardButtonColor.PRIMARY)
    kb.add(Text("Рассылка уведомления"), color=KeyboardButtonColor.SECONDARY)
    kb.row()
    kb.add(Text("Статистика"), color=KeyboardButtonColor.SECONDARY)
    return kb.get_json()


def approve_reject_keyboard(company_id: int) -> str:
    """Инлайн-клавиатура одобрения/отклонения заявки УК.

    Args:
        company_id: ID компании, для которой показывается клавиатура.

    Returns:
        str: JSON-строка инлайн-клавиатуры VK.
    """
    kb = Keyboard(one_time=False, inline=True)
    kb.add(
        Text("Одобрить", payload={"action": "approve", "company_id": company_id}),
        color=KeyboardButtonColor.POSITIVE,
    )
    kb.add(
        Text("Отклонить", payload={"action": "reject", "company_id": company_id}),
        color=KeyboardButtonColor.NEGATIVE,
    )
    return kb.get_json()


def confirm_broadcast_keyboard() -> str:
    """Клавиатура подтверждения рассылки уведомления.

    Returns:
        str: JSON-строка клавиатуры VK.
    """
    kb = Keyboard(one_time=True)
    kb.add(Text("Отправить"), color=KeyboardButtonColor.POSITIVE)
    kb.add(Text("Отмена"), color=KeyboardButtonColor.NEGATIVE)
    return kb.get_json()


def empty_keyboard() -> str:
    """Пустая клавиатура для скрытия ранее показанных кнопок.

    Returns:
        str: JSON-строка пустой клавиатуры VK.
    """
    return Keyboard(one_time=True).get_json()
