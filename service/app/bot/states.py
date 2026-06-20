"""Состояния диалога и хранилище сессий в памяти."""

from enum import Enum


class DialogState(str, Enum):
    """Перечисление состояний диалога бота."""

    IDLE = "idle"

    # Регистрация: выбор роли
    CHOOSE_ROLE = "choose_role"

    # Регистрация УК
    REG_COMPANY_NAME = "reg_company_name"
    REG_COMPANY_PHONE = "reg_company_phone"
    REG_COMPANY_PD_FORM = "reg_company_pd_form"

    # Регистрация сотрудника
    REG_CLEANER_CODE = "reg_cleaner_code"
    REG_CLEANER_CONSENT = "reg_cleaner_consent"

    # Администратор
    ADMIN_BROADCAST_TEXT = "admin_broadcast_text"
    ADMIN_BROADCAST_CONFIRM = "admin_broadcast_confirm"


# In-memory хранилище: {vk_user_id: {"state": DialogState, "data": {...}}}
# Сбрасывается при перезапуске — допустимо для коротких потоков регистрации.
_sessions: dict[int, dict] = {}


def get_session(vk_user_id: int) -> dict:
    """Возвращает сессию пользователя, создавая её при отсутствии.

    Args:
        vk_user_id: VK-ID пользователя.

    Returns:
        dict: Словарь с ключами 'state' и 'data'.
    """
    if vk_user_id not in _sessions:
        _sessions[vk_user_id] = {"state": DialogState.IDLE, "data": {}}
    return _sessions[vk_user_id]


def set_state(vk_user_id: int, state: DialogState, **data) -> None:
    """Устанавливает состояние диалога и обновляет данные сессии.

    Args:
        vk_user_id: VK-ID пользователя.
        state: Новое состояние диалога.
        **data: Дополнительные данные, сохраняемые в сессии.
    """
    session = get_session(vk_user_id)
    session["state"] = state
    session["data"].update(data)


def clear_session(vk_user_id: int) -> None:
    """Удаляет сессию пользователя, сбрасывая его в IDLE.

    Args:
        vk_user_id: VK-ID пользователя.
    """
    _sessions.pop(vk_user_id, None)
