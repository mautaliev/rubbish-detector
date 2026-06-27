"""Обёртки над VK API: отправка сообщений и загрузка фотографий."""

import json
import logging

import aiohttp

logger = logging.getLogger(__name__)


async def send_message(
    api,
    user_id: int,
    text: str,
    keyboard: str | None = None,
    attachment: str | None = None,
) -> None:
    """Отправляет сообщение пользователю через VK API.

    Args:
        api: Объект VK API из vkbottle (message.ctx_api или bot.api).
        user_id: VK-ID получателя.
        text: Текст сообщения.
        keyboard: JSON-строка клавиатуры VK или None.
        attachment: Строка вложений VK (например, 'photo123_456,photo123_789') или None.
    """
    kwargs: dict = {"user_id": user_id, "message": text, "random_id": 0}
    if keyboard is not None:
        kwargs["keyboard"] = keyboard
    if attachment is not None:
        kwargs["attachment"] = attachment
    try:
        await api.messages.send(**kwargs)
    except Exception:
        logger.error("Failed to send message to user %d", user_id, exc_info=True)
        raise


async def upload_doc_for_message(
    api,
    peer_id: int,
    file_bytes: bytes,
    file_name: str,
    content_type: str = "application/octet-stream",
) -> str:
    """Загружает документ в VK как собственный файл бота для отправки в сообщении.

    Args:
        api: Объект VK API из vkbottle.
        peer_id: peer_id диалога, для которого загружается документ.
        file_bytes: Байты файла.
        file_name: Имя файла с расширением (например, 'doc_12345.pdf').
        content_type: MIME-тип файла.

    Returns:
        str: Строка вложения вида 'doc<owner_id>_<doc_id>'.
    """
    upload_server = await api.docs.get_messages_upload_server(peer_id=peer_id, type="doc")

    async with aiohttp.ClientSession() as session:
        form = aiohttp.FormData()
        form.add_field("file", file_bytes, filename=file_name, content_type=content_type)
        async with session.post(upload_server.upload_url, data=form) as resp:
            raw = await resp.text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                raise RuntimeError(
                    f"VK doc upload server returned non-JSON (HTTP {resp.status}): {raw[:300]!r}"
                )

    saved = await api.docs.save(file=data["file"], title=file_name)
    doc = saved.doc
    return f"doc{doc.owner_id}_{doc.id}"


async def upload_photo_for_message(api, peer_id: int, photo_bytes: bytes) -> str:
    """Загружает фото в VK Photos API для отправки в сообщении.

    Выполняет полный цикл загрузки:
      1. Получает upload_url через photos.getMessagesUploadServer
      2. POST изображения на upload_url
      3. Сохраняет через photos.saveMessagesPhoto
      4. Возвращает строку вложения вида 'photo<owner_id>_<photo_id>'

    Args:
        api: Объект VK API из vkbottle.
        peer_id: peer_id диалога, для которого загружается фото.
        photo_bytes: Байты изображения в формате JPEG.

    Returns:
        str: Строка вложения для передачи в messages.send (attachment=...).
    """
    upload_server = await api.photos.get_messages_upload_server(peer_id=peer_id)

    async with aiohttp.ClientSession() as session:
        form = aiohttp.FormData()
        form.add_field("photo", photo_bytes, filename="photo.jpg", content_type="image/jpeg")
        async with session.post(upload_server.upload_url, data=form) as resp:
            raw = await resp.text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                raise RuntimeError(
                    f"VK photo upload server returned non-JSON (HTTP {resp.status}): {raw[:300]!r}"
                )

    logger.debug("VK photo upload response: %s", data)
    photo_field = data.get("photo", "")
    if not photo_field or photo_field in ("[]", "null"):
        raise RuntimeError(
            f"VK photo upload server rejected the image (photo field empty): {data!r}"
        )

    saved = await api.photos.save_messages_photo(
        photo=photo_field,
        server=data["server"],
        hash=data["hash"],
    )
    photo = saved[0]
    return f"photo{photo.owner_id}_{photo.id}"


def build_attachment_str(attachments) -> str:
    """Формирует строку вложений VK из списка attachments входящего сообщения.

    Поддерживает photo, doc, video. Используется для пересылки формы ПД
    от заявителя-УК к администратору.

    access_key включается в строку, когда он есть: без него VK API отклоняет
    пересылку чужих документов между беседами.

    Args:
        attachments: Список объектов вложений из входящего VK-сообщения.

    Returns:
        str: Строка вида 'photo123_456_key,doc789_012_key' для передачи в messages.send.
    """
    parts = []
    for att in attachments or []:
        att_type = att.type.value if hasattr(att.type, "value") else str(att.type)
        if att_type == "photo" and att.photo:
            s = f"photo{att.photo.owner_id}_{att.photo.id}"
            key = getattr(att.photo, "access_key", None)
            if key:
                s += f"_{key}"
            parts.append(s)
        elif att_type == "doc" and att.doc:
            s = f"doc{att.doc.owner_id}_{att.doc.id}"
            key = getattr(att.doc, "access_key", None)
            if key:
                s += f"_{key}"
            parts.append(s)
        elif att_type == "video" and att.video:
            s = f"video{att.video.owner_id}_{att.video.id}"
            key = getattr(att.video, "access_key", None)
            if key:
                s += f"_{key}"
            parts.append(s)
    return ",".join(parts)


def get_photo_url(photo) -> str | None:
    """Возвращает URL максимального доступного размера фото VK.

    Args:
        photo: Объект фотографии из attachments VK-сообщения.

    Returns:
        str | None: URL фото или None, если размеры не доступны.
    """
    if not photo or not photo.sizes:
        return None
    sorted_sizes = sorted(photo.sizes, key=lambda s: (s.width or 0), reverse=True)
    return sorted_sizes[0].url if sorted_sizes else None
