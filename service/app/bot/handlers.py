"""Обработчики сообщений VK-бота по ролям и состояниям диалога."""

import asyncio
import io
import json
import logging
import os
import random
import string
from datetime import datetime, timedelta, timezone
from textwrap import dedent

from PIL import Image

from vkbottle.bot import BotLabeler, Message

from ...db.crud import cleaner as crud_cleaner
from ...db.crud import company as crud_company
from ...db.crud import report as crud_report
from ...db.engine import SessionLocal
from ...db.schemas import CleanerRead, CompanyRead
from ..report_service import create_report
from ..storage import download
from .keyboard import (
    admin_keyboard,
    approve_reject_keyboard,
    confirm_broadcast_keyboard,
    consent_keyboard,
    empty_keyboard,
    role_keyboard,
    withdraw_consent_keyboard,
)
from .states import DialogState, clear_session, get_session, set_state
from .vk_api import get_photo_url, send_message, upload_photo_for_message

logger = logging.getLogger(__name__)
labeler = BotLabeler()

# ---------------------------------------------------------------------------
# Согласие дворника v2 (152-ФЗ, схема «я — оператор»)
# ---------------------------------------------------------------------------

CONSENT_VERSION = "v2"

# Шаблон: {company_name} подставляется при показе конкретной УК.
_CONSENT_TEMPLATE = dedent("""\
    ══ Согласие на обработку персональных данных ══

    Оператор: Мауталиев Саидамир Ислом угли, физическое лицо, ИНН 861008622566,
    контакт: mautalievsaidamir@gmail.com — автор и оператор сервиса «RubbishDetector».

    Я даю Оператору согласие на обработку следующих персональных данных:
    • ФИО (из профиля ВКонтакте)
    • VK-ID
    • фотографии убранных территорий в составе моих отчётов
      (фотографии связаны с моей учётной записью, датой и результатом
      проверки; перед сохранением лица людей и автомобильные номера
      на фотографиях необратимо обезличиваются)

    Цели обработки:
    • контроль качества уборки территорий;
    • передача результатов проверки (фотографий с разметкой и итога
      «чисто/грязно») представителю управляющей компании
      «{company_name}», к которой я прикреплён;
    • улучшение качества распознавания: обезличенные копии фотографий
      могут использоваться для обучения модели.

    Срок хранения: 3 года с момента получения.

    Отозвать согласие можно в любое время командой «Отзыв согласия»
    в этом боте. При отзыве идентифицирующие данные (ФИО, VK-ID)
    удаляются; обезличенная запись сохраняется для истории отчётов.

    Нажмите «Принимаю», чтобы подтвердить согласие,
    или «Отмена» для отказа от регистрации.\
""")

# ---------------------------------------------------------------------------
# Согласие контроллера УК v1 (152-ФЗ, схема «я — оператор»)
# ---------------------------------------------------------------------------

COMPANY_CONSENT_VERSION = "v1"

# Шаблон: {company_name} подставляется по введённому пользователем названию.
_COMPANY_CONSENT_TEMPLATE = dedent("""\
    ══ Согласие на обработку персональных данных ══

    Оператор: Мауталиев Саидамир Ислом угли, физическое лицо, ИНН 861008622566,
    контакт: mautalievsaidamir@gmail.com — автор и оператор сервиса «RubbishDetector».

    Я, представитель управляющей компании «{company_name}», даю
    Оператору согласие на обработку моих персональных данных:
    • VK-ID
    • контактный телефон

    Цель обработки: регистрация компании в сервисе, направление
    уведомлений о результатах проверки уборки, служебные сообщения.

    Срок хранения: 3 года с момента получения.

    Отозвать согласие можно в любое время, направив письмо на адрес
    mautalievsaidamir@gmail.com с указанием названия компании. Обработка
    будет прекращена в срок не более 30 дней с момента получения письма.
    Обратите внимание: при отзыве компания отключается от сервиса,
    её сотрудники теряют возможность направлять отчёты.

    Обратите внимание: фотографии, направляемые вашими сотрудниками,
    после необратимого обезличивания (лица и автомобильные номера)
    могут использоваться для обучения и улучшения модели распознавания.

    Сотрудники дают собственное согласие на обработку своих данных
    при регистрации в боте.

    Нажмите «Принимаю» для завершения регистрации
    или «Отмена» для отказа.\
""")

# VK доставляет несколько фото из одного сообщения как отдельные события через long polling.
# Буферизируем фото каждого дворника и запускаем отчёт после паузы.
_PHOTO_BUFFER_DELAY = 5.0
_photo_buffers: dict[int, dict] = {}


def _to_vk_jpeg(data: bytes) -> bytes:
    """Перекодирует байты изображения в стандартный JPEG, совместимый с VK upload server.

    OpenCV-JPEG иногда содержит нестандартные заголовки, которые VK не принимает
    и возвращает пустое поле photo. PIL гарантирует JFIF-совместимый формат.

    Args:
        data: Байты изображения в любом формате, поддерживаемом PIL.

    Returns:
        bytes: Байты JPEG-изображения.
    """
    img = Image.open(io.BytesIO(data)).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92)
    return buf.getvalue()

_WELCOME_TEXT = (
    "Здравствуйте! Я бот RubbishDetector — автоматический контроль уборки территорий.\n\n"
    "Я анализирую фотографии с помощью компьютерного зрения и определяю, "
    "остался ли мусор после уборки. Результаты проверки с фото отправляются "
    "контроллеру управляющей компании.\n\n"
    "Кто вы?"
)

_REPORT_ACCEPTED = (
    "Отчёт принят. Спасибо что делаете наш город чище!\n\n"
    "📎 Напоминаем: отправленные фото сохраняются и могут использоваться "
    "для улучшения системы распознавания."
)


def _admin_vk_id() -> int | None:
    """Возвращает VK-ID администратора из переменной окружения или None."""
    raw = os.environ.get("ADMIN_VK_ID", "")
    return int(raw) if raw.strip().isdigit() else None


def _gen_invite_code(length: int = 8) -> str:
    """Генерирует случайный буквенно-цифровой invite_code для УК."""
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=length))


# ---------------------------------------------------------------------------
# DB-обёртки для asyncio.to_thread
# ---------------------------------------------------------------------------

def _db_get_company_by_vk(vk_user_id: int) -> CompanyRead | None:
    """Синхронный запрос УК по VK-ID."""
    with SessionLocal() as db:
        return crud_company.get_by_vk_id(db, vk_user_id)


def _db_get_cleaner_by_vk(vk_user_id: int) -> CleanerRead | None:
    """Синхронный запрос дворника по VK-ID."""
    with SessionLocal() as db:
        return crud_cleaner.get_by_vk_id(db, vk_user_id)


def _db_get_company_by_invite(invite_code: str) -> CompanyRead | None:
    """Синхронный запрос УК по коду приглашения (только активные)."""
    with SessionLocal() as db:
        company = crud_company.get_by_invite_code(db, invite_code)
        if company and company.status == 0:
            return company
        return None


def _db_create_company(
    name: str,
    phone: str,
    vk_user_id: int,
    invite_code: str,
    consent_given_at: datetime,
    consent_version: str,
) -> CompanyRead:
    """Синхронное создание записи УК со статусом pending и зафиксированным согласием.

    Args:
        name: Название управляющей компании.
        phone: Контактный телефон контроллера.
        vk_user_id: VK-ID контроллера.
        invite_code: Уникальный invite-код для подключения дворников.
        consent_given_at: UTC-момент нажатия «Принимаю».
        consent_version: Версия текста согласия (напр. 'v1').
    """
    from ...db.schemas import CompanyCreate
    data = CompanyCreate(
        name=name,
        vk_user_id=vk_user_id,
        invite_code=invite_code,
        phone=phone,
        status=1,
        consent_given_at=consent_given_at,
        consent_version=consent_version,
    )
    with SessionLocal() as db:
        return crud_company.create(db, data)


def _db_register_cleaner(
    vk_user_id: int,
    full_name: str,
    company_id: int,
    consent_given_at: datetime,
    consent_version: str,
) -> CleanerRead:
    """Синхронная регистрация дворника с фиксацией факта согласия."""
    with SessionLocal() as db:
        return crud_cleaner.register(
            db,
            vk_user_id,
            full_name,
            company_id,
            consent_given_at=consent_given_at,
            consent_version=consent_version,
        )


def _db_set_company_status(company_id: int, status: int) -> CompanyRead | None:
    """Синхронное обновление статуса УК."""
    with SessionLocal() as db:
        return crud_company.set_status(db, company_id, status)


def _db_list_pending() -> list[CompanyRead]:
    """Синхронный запрос всех заявок УК со статусом pending."""
    with SessionLocal() as db:
        return crud_company.list_pending(db)


def _db_broadcast_vk_ids() -> list[int]:
    """Синхронный запрос VK-ID всех активных пользователей (УК + дворники) для рассылки."""
    with SessionLocal() as db:
        company_ids = crud_company.list_active_vk_ids(db)
        cleaner_ids = crud_cleaner.list_all_vk_ids(db)
    return list(set(company_ids + cleaner_ids))


def _db_mark_notified(report_id) -> None:
    """Синхронная простановка notified_at в отчёте."""
    with SessionLocal() as db:
        crud_report.mark_notified(db, report_id)


def _db_withdraw_consent(vk_user_id: int) -> None:
    """Синхронный отзыв согласия дворника: затирает ПДн и обнуляет vk_user_id."""
    with SessionLocal() as db:
        crud_cleaner.withdraw_consent(db, vk_user_id)


def _db_get_statistics() -> dict:
    """Синхронный сбор статистики системы за три временных интервала.

    Returns:
        dict: Словарь со всеми показателями для формирования сообщения.
    """
    now = datetime.now(tz=timezone.utc)
    since_24h = now - timedelta(hours=24)
    since_7d = now - timedelta(days=7)
    since_30d = now - timedelta(days=30)

    with SessionLocal() as db:
        total_companies = crud_company.count_total_active(db)
        total_cleaners = crud_cleaner.count_total(db)

        new_companies_24h = crud_company.count_new_since(db, since_24h)
        new_companies_7d = crud_company.count_new_since(db, since_7d)
        new_companies_30d = crud_company.count_new_since(db, since_30d)

        new_cleaners_24h = crud_cleaner.count_new_since(db, since_24h)
        new_cleaners_7d = crud_cleaner.count_new_since(db, since_7d)
        new_cleaners_30d = crud_cleaner.count_new_since(db, since_30d)

        r24h, p24h, o24h = crud_report.get_stats_for_period(db, since_24h)
        r7d, p7d, o7d = crud_report.get_stats_for_period(db, since_7d)
        r30d, p30d, o30d = crud_report.get_stats_for_period(db, since_30d)

    return {
        "total_companies": total_companies,
        "total_cleaners": total_cleaners,
        "new_companies": (new_companies_24h, new_companies_7d, new_companies_30d),
        "new_cleaners": (new_cleaners_24h, new_cleaners_7d, new_cleaners_30d),
        "reports": (r24h, r7d, r30d),
        "photos": (p24h, p7d, p30d),
        "objects": (o24h, o7d, o30d),
    }


# ---------------------------------------------------------------------------
# Главный обработчик
# ---------------------------------------------------------------------------

@labeler.message()
async def main_handler(message: Message) -> None:
    """Единая точка входа: маршрутизирует сообщения по роли и состоянию диалога.

    Args:
        message: Входящее VK-сообщение из Long Poll.
    """
    vk_user_id = message.from_id
    api = message.ctx_api
    atts = message.attachments or []
    fwd = message.fwd_messages or []
    att_types = [
        (att.type.value if hasattr(att.type, "value") else str(att.type))
        for att in atts
    ]
    fwd_att_types = [
        [
            (a.type.value if hasattr(a.type, "value") else str(a.type))
            for a in (m.attachments or [])
        ]
        for m in fwd
    ]
    logger.warning(
        "MSG from vk_id=%d text=%r attachments=%d types=%s fwd_msgs=%d is_cropped=%s",
        vk_user_id, (message.text or "")[:40], len(atts), att_types,
        len(fwd), getattr(message, "is_cropped", False),
    )
    session = get_session(vk_user_id)
    state = session["state"]

    # Администратор — высший приоритет
    admin_id = _admin_vk_id()
    if admin_id and vk_user_id == admin_id:
        await _handle_admin(message, session)
        return

    # Маршрутизация по текущему состоянию диалога
    if state == DialogState.REG_COMPANY_NAME:
        await _reg_company_name(message, session)
        return
    if state == DialogState.REG_COMPANY_PHONE:
        await _reg_company_phone(message, session)
        return
    if state == DialogState.REG_COMPANY_CONSENT:
        await _reg_company_consent(message, session)
        return
    if state == DialogState.REG_CLEANER_CODE:
        await _reg_cleaner_code(message, session)
        return
    if state == DialogState.REG_CLEANER_CONSENT:
        await _reg_cleaner_consent(message, session)
        return
    if state == DialogState.CLEANER_WITHDRAW_CONFIRM:
        await _cleaner_withdraw_confirm(message, session)
        return

    # IDLE — проверяем, кто пишет, через БД
    company = await asyncio.to_thread(_db_get_company_by_vk, vk_user_id)
    if company is not None:
        await _handle_company_user(api, vk_user_id, company)
        return

    cleaner = await asyncio.to_thread(_db_get_cleaner_by_vk, vk_user_id)
    if cleaner is not None:
        await _handle_cleaner_message(message, cleaner)
        return

    # Не зарегистрирован — обрабатываем нажатия кнопок ролей или показываем приветствие
    text = (message.text or "").strip()
    if text == "Упр. организация":
        set_state(vk_user_id, DialogState.REG_COMPANY_NAME)
        await send_message(api, vk_user_id, "Введите название вашей управляющей компании.")
        return
    if text == "Сотрудник по уборке":
        set_state(vk_user_id, DialogState.REG_CLEANER_CODE)
        await send_message(
            api,
            vk_user_id,
            "Введите регистрационный код, который вам выдала управляющая компания.",
        )
        return

    await send_message(api, vk_user_id, _WELCOME_TEXT, keyboard=role_keyboard())


# ---------------------------------------------------------------------------
# Обработчики по роли пользователя
# ---------------------------------------------------------------------------

async def _handle_company_user(api, vk_user_id: int, company: CompanyRead) -> None:
    """Обрабатывает сообщение от зарегистрированного пользователя-УК.

    Args:
        api: VK API.
        vk_user_id: VK-ID отправителя.
        company: Данные УК из БД.
    """
    if company.status == 0:
        # Активный контроллер — информируем о статусе и invite_code
        await send_message(
            api,
            vk_user_id,
            f"Вы зарегистрированы как контроллер компании «{company.name}».\n"
            f"Код для подключения дворников: {company.invite_code}\n\n"
            "Уведомления о результатах проверки приходят вам автоматически.",
        )
    elif company.status == 1:
        await send_message(
            api,
            vk_user_id,
            f"Ваша заявка на регистрацию компании «{company.name}» находится "
            "на рассмотрении. Мы уведомим вас о результате.",
        )
    else:
        # status == 2: denied
        await send_message(
            api,
            vk_user_id,
            "К сожалению, ваша заявка на регистрацию была отклонена. "
            "Для уточнения деталей свяжитесь с администрацией сервиса.",
        )


async def _handle_cleaner_message(message: Message, cleaner: CleanerRead) -> None:
    """Обрабатывает сообщение от зарегистрированного дворника.

    VK доставляет несколько фото одного сообщения как отдельные события,
    поэтому фото буферизируются на _PHOTO_BUFFER_DELAY секунд перед отправкой в обработку.

    Args:
        message: Входящее VK-сообщение.
        cleaner: Данные дворника из БД.
    """
    api = message.ctx_api
    vk_user_id = message.from_id

    text = (message.text or "").strip()
    if text == "Отзыв согласия":
        set_state(vk_user_id, DialogState.CLEANER_WITHDRAW_CONFIRM)
        await send_message(
            api,
            vk_user_id,
            "Вы собираетесь отозвать согласие на обработку персональных данных.\n\n"
            "После подтверждения ваши ФИО и VK-ID будут удалены из системы. "
            "Вы перестанете быть зарегистрированным дворником и не сможете отправлять отчёты.\n\n"
            "Отчёты, отправленные ранее, сохранятся в обезличенном виде.\n\n"
            "Подтвердите отзыв согласия.",
            keyboard=withdraw_consent_keyboard(),
        )
        return

    def _is_photo(att) -> bool:
        return (att.type.value if hasattr(att.type, "value") else str(att.type)) == "photo"

    # is_cropped=True: VK обрезал сообщение, передав только первое вложение.
    # Запрашиваем полный объект через messages.getById.
    if getattr(message, "is_cropped", False):
        try:
            resp = await api.messages.get_by_id(message_ids=[message.id])
            full_atts = resp.items[0].attachments if (resp and resp.items) else (message.attachments or [])
            logger.warning(
                "is_cropped: fetched full msg, attachments=%d", len(full_atts or [])
            )
        except Exception:
            logger.error("is_cropped: failed to fetch full message", exc_info=True)
            full_atts = message.attachments or []
    else:
        full_atts = message.attachments or []

    photo_atts = [att for att in (full_atts or []) if _is_photo(att)]
    for fwd_msg in (message.fwd_messages or []):
        photo_atts += [att for att in (fwd_msg.attachments or []) if _is_photo(att)]

    non_photo_atts = [
        att for att in (message.attachments or [])
        if not _is_photo(att)
    ]

    if not photo_atts:
        if non_photo_atts:
            await send_message(
                api,
                vk_user_id,
                "Я могу обработать только фотографии. Пришлите фото как обычное "
                "вложение, а не как документ.",
            )
        else:
            await send_message(
                api,
                vk_user_id,
                "Для отправки отчёта пришлите одно или несколько фото убранного участка. "
                "К фото можно добавить текстовый комментарий.",
            )
        return

    is_new_buffer = vk_user_id not in _photo_buffers
    if is_new_buffer:
        _photo_buffers[vk_user_id] = {"photo_atts": [], "comment": None, "task": None}

    buf = _photo_buffers[vk_user_id]
    buf["photo_atts"].extend(photo_atts)
    logger.warning(
        "Cleaner vk=%d: received %d photo(s), buffer total=%d",
        vk_user_id, len(photo_atts), len(buf["photo_atts"]),
    )
    if not buf["comment"]:
        buf["comment"] = (message.text or "").strip() or None

    # Мгновенный ответ только при первом фото из серии
    if is_new_buffer:
        await send_message(api, vk_user_id, "Фото получены, обрабатываю...")

    # Перезапускаем таймер: отсчёт ведётся от последнего полученного фото
    if buf["task"] and not buf["task"].done():
        buf["task"].cancel()
    buf["task"] = asyncio.create_task(_flush_photo_buffer(api, vk_user_id, cleaner))


async def _flush_photo_buffer(api, vk_user_id: int, cleaner: CleanerRead) -> None:
    """Ждёт окончания серии фото и запускает обработку отчёта.

    Args:
        api: VK API.
        vk_user_id: VK-ID дворника.
        cleaner: Данные дворника из БД.
    """
    try:
        await asyncio.sleep(_PHOTO_BUFFER_DELAY)
    except asyncio.CancelledError:
        return  # пришли новые фото — новый таймер уже запущен

    buf = _photo_buffers.pop(vk_user_id, None)
    if not buf or not buf["photo_atts"]:
        return

    logger.warning(
        "Flushing buffer for vk=%d: %d photo(s)", vk_user_id, len(buf["photo_atts"])
    )
    try:
        await _process_report(api, vk_user_id, cleaner, buf["photo_atts"], buf["comment"])
    except Exception:
        logger.error("_process_report crashed for vk=%d", vk_user_id, exc_info=True)


# ---------------------------------------------------------------------------
# Обработка отчёта в фоне
# ---------------------------------------------------------------------------

async def _process_report(api, vk_user_id: int, cleaner: CleanerRead, photo_atts, comment: str | None) -> None:
    """Скачивает фото, запускает детекцию, сохраняет отчёт, уведомляет контроллера.

    Args:
        api: VK API.
        vk_user_id: VK-ID дворника.
        cleaner: Данные дворника.
        photo_atts: Список вложений-фотографий из входящего сообщения.
        comment: Текстовый комментарий дворника или None.
    """
    # Скачиваем фото с CDN VK
    logger.warning("_process_report: vk=%d atts=%d", vk_user_id, len(photo_atts))
    photo_bytes_list: list[bytes] = []
    for att in photo_atts:
        url = get_photo_url(att.photo)
        if not url:
            logger.warning("vk=%d: no URL for attachment, skipping", vk_user_id)
            continue
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    data = await resp.read()
                    photo_bytes_list.append(data)
                    logger.warning("vk=%d: downloaded %d bytes", vk_user_id, len(data))
        except Exception:
            logger.error("Failed to download photo from VK CDN: %s", url, exc_info=True)

    logger.warning("vk=%d: downloaded %d/%d", vk_user_id, len(photo_bytes_list), len(photo_atts))
    if not photo_bytes_list:
        await send_message(
            api,
            vk_user_id,
            "Не удалось загрузить фото. Попробуйте отправить отчёт ещё раз.",
        )
        return

    company = await asyncio.to_thread(_db_get_company_by_id, cleaner.company_id)
    if company is None:
        logger.error("Company %d not found for cleaner %d", cleaner.company_id, cleaner.id)
        return
    if company.status != 0:
        await send_message(
            api,
            vk_user_id,
            "Ваша управляющая компания отключена от сервиса. "
            "Отправка отчётов недоступна.",
        )
        return

    try:
        report = await create_report(
            cleaner_id=cleaner.id,
            company_id=cleaner.company_id,
            model_version=company.default_model,
            photo_bytes_list=photo_bytes_list,
            comment=comment,
        )
    except ValueError:
        await send_message(
            api,
            vk_user_id,
            "Не удалось обработать фото. Попробуйте отправить отчёт ещё раз.",
        )
        return

    # Ответ дворнику — всегда одинаковый
    await send_message(api, vk_user_id, _REPORT_ACCEPTED)

    # Уведомление контроллера
    await _notify_company(api, cleaner, company, report)


def _db_get_company_by_id(company_id: int) -> CompanyRead | None:
    """Синхронный запрос УК по первичному ключу."""
    with SessionLocal() as db:
        return crud_company.get_by_id(db, company_id)


async def _upload_photo_with_retry(
    api,
    peer_id: int,
    photo_bytes: bytes,
    key: str,
    *,
    attempts: int = 5,
    delay: float = 2.0,
) -> str | None:
    """Пытается загрузить фото в VK до `attempts` раз с паузой `delay` секунд.

    Args:
        api: VK API объект.
        peer_id: VK-ID получателя (peer_id для photos.getMessagesUploadServer).
        photo_bytes: Байты JPEG-изображения.
        key: S3-ключ фото (только для логирования).
        attempts: Максимальное число попыток (по умолчанию 5).
        delay: Пауза между попытками в секундах.

    Returns:
        str | None: Строка вложения ('photo<owner>_<id>') или None после всех неудач.
    """
    for attempt in range(1, attempts + 1):
        try:
            return await upload_photo_for_message(api, peer_id, photo_bytes)
        except Exception:
            logger.warning(
                "VK photo upload attempt %d/%d failed for key %s",
                attempt, attempts, key, exc_info=True,
            )
            if attempt < attempts:
                await asyncio.sleep(delay)
    return None


async def _notify_company(api, cleaner: CleanerRead, company: CompanyRead, report) -> None:
    """Отправляет уведомление контроллеру УК с фото и результатом проверки.

    Args:
        api: VK API.
        cleaner: Данные дворника.
        company: Данные УК.
        report: Созданный отчёт из БД.
    """
    controller_vk_id = company.vk_user_id
    if controller_vk_id is None:
        logger.warning("Company %d has no vk_user_id, skipping notification", company.id)
        return
    date_str = report.created_at.strftime("%d.%m.%Y %H:%M")
    comment_str = report.comment or "—"

    # Определяем, какие фото отправляем: для чистых — original, для грязных — detected
    if report.is_clean:
        icon = "✅"
        status_text = "После уборки от дворника мусора обнаружено не было."
        keys = [p["original_key"] for p in report.photos]
    else:
        dirty_count = sum(1 for p in report.photos if not p["is_clean"])
        icon = "❌"
        status_text = (
            f"Обнаружен мусор: {report.objects_count} объектов "
            f"на {dirty_count} фото."
        )
        keys = [p["detected_key"] for p in report.photos]

    text = (
        f"{icon} Отчёт от дворника {cleaner.full_name}\n"
        f"Дата: {date_str}\n"
        f"Комментарий: {comment_str}\n\n"
        f"{status_text}"
    )

    # Загружаем фото из S3 и отправляем через VK Photos API
    attachment_parts: list[str] = []
    for key in keys:
        try:
            photo_bytes = await download(key)
            photo_bytes = await asyncio.to_thread(_to_vk_jpeg, photo_bytes)
        except Exception:
            logger.error("Failed to download/convert photo for key %s", key, exc_info=True)
            continue
        att_str = await _upload_photo_with_retry(api, controller_vk_id, photo_bytes, key)
        if att_str is not None:
            attachment_parts.append(att_str)

    attachment = ",".join(attachment_parts) if attachment_parts else None

    try:
        await send_message(api, controller_vk_id, text, attachment=attachment)
        await asyncio.to_thread(_db_mark_notified, report.id)
    except Exception:
        logger.error(
            "Failed to notify company %d about report %s",
            company.id, report.id,
            exc_info=True,
        )


# ---------------------------------------------------------------------------
# Регистрация УК
# ---------------------------------------------------------------------------

async def _reg_company_name(message: Message, session: dict) -> None:
    """Шаг 1 регистрации УК: получение названия компании.

    Args:
        message: Входящее сообщение.
        session: Текущая сессия пользователя.
    """
    name = (message.text or "").strip()
    if not name:
        await send_message(message.ctx_api, message.from_id, "Пожалуйста, введите название компании.")
        return
    set_state(message.from_id, DialogState.REG_COMPANY_PHONE, company_name=name)
    await send_message(message.ctx_api, message.from_id, "Укажите контактный номер телефона.")


async def _reg_company_phone(message: Message, session: dict) -> None:
    """Шаг 2 регистрации УК: получение контактного телефона.

    После ввода телефона показывает текст согласия на обработку ПДн
    с кнопками «Принимаю / Отмена».

    Args:
        message: Входящее сообщение.
        session: Текущая сессия пользователя.
    """
    phone = (message.text or "").strip()
    if not phone:
        await send_message(message.ctx_api, message.from_id, "Пожалуйста, введите номер телефона.")
        return

    api = message.ctx_api
    vk_user_id = message.from_id
    company_name = session["data"]["company_name"]

    set_state(vk_user_id, DialogState.REG_COMPANY_CONSENT, company_phone=phone)
    await send_message(
        api,
        vk_user_id,
        _COMPANY_CONSENT_TEMPLATE.format(company_name=company_name),
        keyboard=consent_keyboard(),
    )


async def _reg_company_consent(message: Message, session: dict) -> None:
    """Шаг 3 регистрации УК: подтверждение согласия на обработку ПДн контроллера.

    По нажатию «Принимаю» фиксирует consent_given_at и создаёт запись УК
    со статусом pending. Карточку без вложений отправляет администратору.

    Args:
        message: Входящее сообщение.
        session: Текущая сессия пользователя.
    """
    api = message.ctx_api
    vk_user_id = message.from_id
    text = (message.text or "").strip()

    if text == "Отмена":
        clear_session(vk_user_id)
        await send_message(api, vk_user_id, "Регистрация отменена.", keyboard=role_keyboard())
        return

    if text != "Принимаю":
        await send_message(api, vk_user_id, "Пожалуйста, нажмите одну из кнопок.", keyboard=consent_keyboard())
        return

    name = session["data"]["company_name"]
    phone = session["data"]["company_phone"]
    invite_code = _gen_invite_code()

    # Фиксируем момент согласия до любых сетевых запросов
    consent_ts = datetime.now(tz=timezone.utc)

    company = await asyncio.to_thread(
        _db_create_company, name, phone, vk_user_id, invite_code, consent_ts, COMPANY_CONSENT_VERSION
    )

    admin_id = _admin_vk_id()
    if admin_id:
        admin_text = (
            f"Новая заявка на регистрацию УК:\n"
            f"Название: {name}\n"
            f"Телефон: {phone}\n"
            f"VK: vk.com/id{vk_user_id}"
        )
        try:
            await api.messages.send(
                user_id=admin_id,
                message=admin_text,
                keyboard=approve_reject_keyboard(company.id),
                random_id=0,
            )
        except Exception:
            logger.error("Failed to notify admin about new company %d", company.id, exc_info=True)

    clear_session(vk_user_id)
    await send_message(
        api,
        vk_user_id,
        "Спасибо! Ваша заявка отправлена на рассмотрение. Мы уведомим вас о результате.",
    )


# ---------------------------------------------------------------------------
# Регистрация дворника
# ---------------------------------------------------------------------------

async def _reg_cleaner_code(message: Message, session: dict) -> None:
    """Шаг 1 регистрации дворника: проверка invite_code.

    Args:
        message: Входящее сообщение.
        session: Текущая сессия пользователя.
    """
    api = message.ctx_api
    vk_user_id = message.from_id

    # Если пришло фото — просим ввести код сначала
    if message.attachments:
        await send_message(api, vk_user_id, "Пожалуйста, сначала введите регистрационный код.")
        return

    code = (message.text or "").strip()
    if not code:
        await send_message(api, vk_user_id, "Введите регистрационный код.")
        return

    company = await asyncio.to_thread(_db_get_company_by_invite, code)
    if company is None:
        await send_message(
            api,
            vk_user_id,
            "Код не найден. Проверьте правильность ввода или обратитесь "
            "к представителю вашей управляющей компании.",
        )
        return

    set_state(vk_user_id, DialogState.REG_CLEANER_CONSENT, company_id=company.id, company_name=company.name)
    await send_message(
        api,
        vk_user_id,
        _CONSENT_TEMPLATE.format(company_name=company.name),
        keyboard=consent_keyboard(),
    )


async def _reg_cleaner_consent(message: Message, session: dict) -> None:
    """Шаг 2 регистрации дворника: подтверждение согласия.

    Args:
        message: Входящее сообщение.
        session: Текущая сессия пользователя.
    """
    api = message.ctx_api
    vk_user_id = message.from_id
    text = (message.text or "").strip()

    if text == "Отмена":
        clear_session(vk_user_id)
        await send_message(api, vk_user_id, "Регистрация отменена.", keyboard=role_keyboard())
        return

    if text != "Принимаю":
        await send_message(api, vk_user_id, "Пожалуйста, нажмите одну из кнопок.", keyboard=consent_keyboard())
        return

    company_id = session["data"]["company_id"]
    company_name = session["data"]["company_name"]

    # Фиксируем момент согласия до любых сетевых запросов
    consent_ts = datetime.now(tz=timezone.utc)

    # Получаем имя из VK-профиля
    try:
        users = await api.users.get(user_ids=[vk_user_id])
        full_name = f"{users[0].first_name} {users[0].last_name}"
    except Exception:
        full_name = f"Пользователь VK {vk_user_id}"

    await asyncio.to_thread(
        _db_register_cleaner,
        vk_user_id,
        full_name,
        company_id,
        consent_ts,
        CONSENT_VERSION,
    )
    clear_session(vk_user_id)

    await send_message(
        api,
        vk_user_id,
        f"Вы зарегистрированы в компании «{company_name}».\n\n"
        "Для отправки отчёта просто пришлите мне фотографии убранного участка. "
        "К фото можно добавить текстовый комментарий (адрес, номер участка и т.п.).",
        keyboard=empty_keyboard(),
    )


# ---------------------------------------------------------------------------
# Отзыв согласия дворника
# ---------------------------------------------------------------------------

async def _cleaner_withdraw_confirm(message: Message, session: dict) -> None:
    """Обрабатывает подтверждение или отмену отзыва согласия дворника.

    Args:
        message: Входящее сообщение.
        session: Текущая сессия пользователя.
    """
    api = message.ctx_api
    vk_user_id = message.from_id
    text = (message.text or "").strip()

    if text == "Отмена":
        clear_session(vk_user_id)
        await send_message(
            api,
            vk_user_id,
            "Отзыв согласия отменён. Вы по-прежнему зарегистрированы в системе.",
            keyboard=empty_keyboard(),
        )
        return

    if text != "Подтвердить отзыв":
        await send_message(
            api,
            vk_user_id,
            "Пожалуйста, нажмите одну из кнопок.",
            keyboard=withdraw_consent_keyboard(),
        )
        return

    await asyncio.to_thread(_db_withdraw_consent, vk_user_id)
    clear_session(vk_user_id)
    await send_message(
        api,
        vk_user_id,
        "Ваше согласие отозвано. Идентифицирующие данные (ФИО, VK-ID) удалены "
        "из системы; обезличенная запись сохранена для истории отчётов.\n\n"
        "Для повторного использования бота потребуется заново пройти регистрацию.",
        keyboard=role_keyboard(),
    )


# ---------------------------------------------------------------------------
# Администратор
# ---------------------------------------------------------------------------

async def _handle_admin(message: Message, session: dict) -> None:
    """Обрабатывает все сообщения от администратора.

    Args:
        message: Входящее сообщение.
        session: Текущая сессия администратора.
    """
    api = message.ctx_api
    vk_user_id = message.from_id
    state = session["state"]
    text = (message.text or "").strip()

    # Состояния рассылки
    if state == DialogState.ADMIN_BROADCAST_TEXT:
        await _admin_broadcast_text(message, session)
        return
    if state == DialogState.ADMIN_BROADCAST_CONFIRM:
        await _admin_broadcast_confirm(message, session)
        return

    # Обработка payload кнопок одобрения/отклонения
    if message.payload:
        try:
            payload = json.loads(message.payload)
            action = payload.get("action")
            company_id = payload.get("company_id")
            if action in ("approve", "reject") and company_id:
                await _admin_process_decision(api, vk_user_id, action, int(company_id))
                return
        except (json.JSONDecodeError, ValueError):
            pass

    # Кнопки главного меню
    if text == "Заявки на регистрацию":
        await _admin_show_pending(api, vk_user_id)
        return
    if text == "Рассылка уведомления":
        set_state(vk_user_id, DialogState.ADMIN_BROADCAST_TEXT)
        await send_message(
            api,
            vk_user_id,
            "Введите текст уведомления. Оно будет отправлено всем "
            "зарегистрированным пользователям (УК и сотрудники).",
            keyboard=empty_keyboard(),
        )
        return
    if text == "Статистика":
        await _admin_show_statistics(api, vk_user_id)
        return

    # Любое другое сообщение → главная панель
    await send_message(api, vk_user_id, "Панель администратора.", keyboard=admin_keyboard())


async def _admin_show_statistics(api, vk_user_id: int) -> None:
    """Собирает и отправляет администратору статистику использования приложения.

    Данные формируются за три периода: последние 24 часа, 7 дней и 30 дней.
    Всё отправляется одним сообщением.

    Args:
        api: VK API.
        vk_user_id: VK-ID администратора.
    """
    stats = await asyncio.to_thread(_db_get_statistics)

    nc = stats["new_companies"]
    nw = stats["new_cleaners"]
    r = stats["reports"]
    p = stats["photos"]
    o = stats["objects"]

    text = (
        "📊 Статистика системы\n\n"
        f"🏢 Управляющих компаний (активных): {stats['total_companies']}\n"
        f"👷 Дворников: {stats['total_cleaners']}\n\n"
        "Новые регистрации:\n"
        f"📅 За 24 часа — УК: {nc[0]}, дворников: {nw[0]}\n"
        f"📅 За 7 дней — УК: {nc[1]}, дворников: {nw[1]}\n"
        f"📅 За 30 дней — УК: {nc[2]}, дворников: {nw[2]}\n\n"
        "Активность системы:\n"
        f"⏱ За 24 часа — отчётов: {r[0]}, изображений: {p[0]}, объектов мусора: {o[0]}\n"
        f"⏱ За 7 дней — отчётов: {r[1]}, изображений: {p[1]}, объектов мусора: {o[1]}\n"
        f"⏱ За 30 дней — отчётов: {r[2]}, изображений: {p[2]}, объектов мусора: {o[2]}"
    )
    await send_message(api, vk_user_id, text, keyboard=admin_keyboard())


async def _admin_show_pending(api, vk_user_id: int) -> None:
    """Показывает список заявок на регистрацию со статусом pending.

    Args:
        api: VK API.
        vk_user_id: VK-ID администратора.
    """
    pending = await asyncio.to_thread(_db_list_pending)
    if not pending:
        await send_message(api, vk_user_id, "Нет заявок на рассмотрении.", keyboard=admin_keyboard())
        return

    for company in pending:
        card_text = (
            f"Заявка #{company.id}\n"
            f"Название: {company.name}\n"
            f"Телефон: {company.phone or 'не указан'}\n"
            f"VK: vk.com/id{company.vk_user_id}"
        )
        await send_message(api, vk_user_id, card_text, keyboard=approve_reject_keyboard(company.id))


async def _admin_process_decision(api, admin_vk_id: int, action: str, company_id: int) -> None:
    """Применяет решение администратора: одобряет или отклоняет заявку УК.

    Args:
        api: VK API.
        admin_vk_id: VK-ID администратора.
        action: 'approve' или 'reject'.
        company_id: ID компании из payload кнопки.
    """
    if action == "approve":
        company = await asyncio.to_thread(_db_set_company_status, company_id, 0)
        if company:
            await send_message(
                api,
                company.vk_user_id,
                f"Ваша компания «{company.name}» зарегистрирована.\n\n"
                f"Код для подключения сотрудников: {company.invite_code}\n\n"
                "Сообщите этот код вашим сотрудникам по уборке — они вводят его "
                "в этот бот, после чего могут присылать фото-отчёты. Вы будете "
                "получать уведомления о результатах проверки в этот чат.",
            )
            await send_message(
                api,
                admin_vk_id,
                f"✅ Заявка компании «{company.name}» принята.",
            )
        await _admin_show_pending(api, admin_vk_id)
    else:
        company = await asyncio.to_thread(_db_set_company_status, company_id, 2)
        if company:
            await send_message(
                api,
                company.vk_user_id,
                "К сожалению, ваша заявка на регистрацию отклонена. "
                "Для уточнения деталей свяжитесь с администрацией сервиса.",
            )
            await send_message(
                api,
                admin_vk_id,
                f"❌ Заявка компании «{company.name}» отклонена.",
            )
        await _admin_show_pending(api, admin_vk_id)


async def _admin_broadcast_text(message: Message, session: dict) -> None:
    """Получает текст рассылки и запрашивает подтверждение.

    Args:
        message: Входящее сообщение с текстом рассылки.
        session: Текущая сессия администратора.
    """
    api = message.ctx_api
    vk_user_id = message.from_id
    text = (message.text or "").strip()

    if not text:
        await send_message(api, vk_user_id, "Введите текст уведомления.")
        return

    recipients = await asyncio.to_thread(_db_broadcast_vk_ids)
    n = len(recipients)
    set_state(vk_user_id, DialogState.ADMIN_BROADCAST_CONFIRM, broadcast_text=text, recipients=recipients)

    await send_message(
        api,
        vk_user_id,
        f"Отправить это сообщение всем пользователям ({n} человек)?\n\n{text}",
        keyboard=confirm_broadcast_keyboard(),
    )


async def _admin_broadcast_confirm(message: Message, session: dict) -> None:
    """Выполняет рассылку или отменяет её по решению администратора.

    Args:
        message: Входящее сообщение с подтверждением или отменой.
        session: Текущая сессия администратора.
    """
    api = message.ctx_api
    vk_user_id = message.from_id
    text = (message.text or "").strip()

    if text == "Отмена":
        clear_session(vk_user_id)
        await send_message(api, vk_user_id, "Рассылка отменена.", keyboard=admin_keyboard())
        return

    if text != "Отправить":
        await send_message(api, vk_user_id, "Нажмите «Отправить» или «Отмена».", keyboard=confirm_broadcast_keyboard())
        return

    broadcast_text = session["data"]["broadcast_text"]
    recipients: list[int] = session["data"]["recipients"]
    clear_session(vk_user_id)

    ok, err = 0, 0
    for uid in recipients:
        try:
            await api.messages.send(user_id=uid, message=broadcast_text, random_id=0)
            ok += 1
        except Exception:
            err += 1

    if err == 0:
        result_text = f"Уведомление отправлено {ok} пользователям."
    else:
        result_text = f"Уведомление отправлено. Доставлено: {ok}, не доставлено: {err}."

    await send_message(api, vk_user_id, result_text, keyboard=admin_keyboard())


def register_handlers(bot) -> None:
    """Регистрирует labeler с обработчиками в экземпляре бота.

    Args:
        bot: Экземпляр vkbottle Bot.
    """
    bot.labeler.load(labeler)
