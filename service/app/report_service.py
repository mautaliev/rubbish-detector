"""Бизнес-логика создания отчёта: детекция → S3 → БД.

Используется только VK-ботом. Веб-интерфейс (/api/detect, /api/detect-file)
работает независимо и не вызывает этот модуль.
"""

import asyncio
import io
import logging

from PIL import Image

from .anonymize import anonymize_bytes
from .detector import detect
from .storage import save_pair
from ..db.crud import report as crud_report
from ..db.engine import SessionLocal
from ..db.models import ModelVersion
from ..db.schemas import PhotoResult, ReportCreate, ReportRead

logger = logging.getLogger(__name__)


async def create_report(
    cleaner_id: int,
    company_id: int,
    model_version: ModelVersion,
    photo_bytes_list: list[bytes],
    comment: str | None,
) -> ReportRead:
    """Создаёт отчёт дворника: детекция, сохранение в S3 и запись в БД.

    Для каждого фото:
      1. decode → PIL.Image
      2. detect() из detector.py (тот же код, что и в веб-интерфейсе)
      3. save_pair() из storage.py → ключи S3
      4. формирует PhotoResult

    Если фото не удалось обработать — пропускается. Если все фото не удались —
    выбрасывает ValueError.

    Args:
        cleaner_id: ID дворника из таблицы cleaner.
        company_id: ID управляющей компании из таблицы company.
        model_version: Версия модели (берётся из company.default_model на момент создания).
        photo_bytes_list: Список байт исходных фотографий.
        comment: Текстовый комментарий дворника или None.

    Returns:
        ReportRead: Созданный отчёт из БД.

    Raises:
        ValueError: Если ни одно фото не удалось обработать.
    """
    detect_class = model_version == ModelVersion.multi_class

    logger.warning(
        "create_report: cleaner=%d company=%d photos_in=%d",
        cleaner_id, company_id, len(photo_bytes_list),
    )
    photos: list[PhotoResult] = []
    for idx, photo_bytes in enumerate(photo_bytes_list):
        try:
            img = Image.open(io.BytesIO(photo_bytes)).convert("RGB")
            result = await asyncio.to_thread(detect, img, detect_class, 0.25)

            if result["image"] is not None:
                buf = io.BytesIO()
                result["image"].save(buf, format="JPEG", quality=92)
                detected_bytes = buf.getvalue()
            else:
                detected_bytes = photo_bytes

            original_anon = await asyncio.to_thread(anonymize_bytes, photo_bytes)
            detected_anon = await asyncio.to_thread(anonymize_bytes, detected_bytes)
            saved = await save_pair(company_id, original_anon, detected_anon)

            classes: dict[str, int] = {}
            if result["found"]:
                classes = {k: v["count"] for k, v in result["found"].items()}

            photos.append(
                PhotoResult(
                    original_key=saved["keys"]["original"],
                    detected_key=saved["keys"]["detected"],
                    total_objects=result["total"],
                    classes=classes,
                    is_clean=(result["total"] == 0),
                )
            )
            logger.warning(
                "create_report: photo %d/%d OK (objects=%d)",
                idx + 1, len(photo_bytes_list), result["total"],
            )
        except Exception:
            logger.error(
                "create_report: photo %d/%d FAILED cleaner=%d",
                idx + 1, len(photo_bytes_list), cleaner_id,
                exc_info=True,
            )

    logger.warning(
        "create_report: saved %d/%d for cleaner=%d",
        len(photos), len(photo_bytes_list), cleaner_id,
    )
    if not photos:
        raise ValueError("No photos could be processed")

    report_data = ReportCreate(
        cleaner_id=cleaner_id,
        company_id=company_id,
        model_version=model_version,
        photos=photos,
        comment=comment,
    )
    return await asyncio.to_thread(_save_report, report_data)


def _save_report(data: ReportCreate) -> ReportRead:
    """Синхронная запись отчёта в БД.

    Args:
        data: Данные отчёта с уже обработанными фото.

    Returns:
        ReportRead: Созданный отчёт.
    """
    with SessionLocal() as db:
        return crud_report.create_report(db, data)
