"""CRUD-операции для отчётов дворников."""

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..models import Report
from ..schemas import ReportCreate, ReportRead


def create_report(db: Session, data: ReportCreate) -> ReportRead:
    """Создаёт отчёт и вычисляет агрегаты по массиву фото.

    Агрегаты рассчитываются здесь, а не на стороне БД, чтобы логика
    была явной и тестируемой без SQL:
    - photos_count  = количество элементов в photos;
    - objects_count = сумма total_objects по всем фото;
    - is_clean      = True только если все фото чистые.

    Pydantic-объекты PhotoResult сериализуются в dict перед записью,
    так как SQLAlchemy хранит поле photos как JSONB.
    """
    photos_dicts = [p.model_dump() for p in data.photos]

    photos_count = len(data.photos)
    objects_count = sum(p.total_objects for p in data.photos)
    is_clean = all(p.is_clean for p in data.photos)

    report = Report(
        cleaner_id=data.cleaner_id,
        company_id=data.company_id,
        comment=data.comment,
        model_version=data.model_version,
        photos=photos_dicts,
        is_clean=is_clean,
        photos_count=photos_count,
        objects_count=objects_count,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return ReportRead.model_validate(report)


def mark_notified(db: Session, report_id: uuid.UUID) -> ReportRead | None:
    """Проставляет время уведомления контроллера.

    Вызывается после того, как бот успешно отправил сообщение в VK
    на vk_user_id УК. Если отчёт не найден — возвращает None.
    """
    report = db.get(Report, report_id)
    if report is None:
        return None
    report.notified_at = datetime.now(tz=timezone.utc)
    db.commit()
    db.refresh(report)
    return ReportRead.model_validate(report)


def list_by_company(
    db: Session, company_id: int, limit: int = 50, offset: int = 0
) -> list[ReportRead]:
    """Возвращает отчёты УК, отсортированные от новых к старым.

    Использует денормализованный company_id в таблице report,
    поэтому join через cleaner не нужен. Поддерживает пагинацию.
    """
    reports = (
        db.query(Report)
        .filter(Report.company_id == company_id)
        .order_by(Report.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [ReportRead.model_validate(r) for r in reports]


def list_by_cleaner(
    db: Session, cleaner_id: int, limit: int = 50, offset: int = 0
) -> list[ReportRead]:
    """Возвращает отчёты конкретного дворника, отсортированные от новых к старым."""
    reports = (
        db.query(Report)
        .filter(Report.cleaner_id == cleaner_id)
        .order_by(Report.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [ReportRead.model_validate(r) for r in reports]


def get_by_id(db: Session, report_id: uuid.UUID) -> ReportRead | None:
    """Возвращает отчёт по UUID или None, если не найден."""
    report = db.get(Report, report_id)
    return ReportRead.model_validate(report) if report else None
