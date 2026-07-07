"""CRUD-операции для управляющих компаний (УК)."""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..models import Company
from ..schemas import CompanyCreate, CompanyRead


def create(db: Session, data: CompanyCreate) -> CompanyRead:
    """Создаёт новую УК и возвращает её из БД (с заполненными id и created_at).

    Args:
        db: Сессия SQLAlchemy.
        data: Данные для создания УК, включая поля согласия.
    """
    company = Company(**data.model_dump())
    db.add(company)
    db.commit()
    db.refresh(company)
    return CompanyRead.model_validate(company)


def get_by_id(db: Session, company_id: int) -> CompanyRead | None:
    """Возвращает УК по первичному ключу или None, если не найдена."""
    company = db.get(Company, company_id)
    return CompanyRead.model_validate(company) if company else None


def get_by_invite_code(db: Session, invite_code: str) -> CompanyRead | None:
    """Возвращает УК по коду приглашения или None, если код не существует.

    Используется на первом шаге регистрации дворника: бот передаёт
    invite_code из сообщения, чтобы определить, к какой УК привязать дворника.
    """
    company = db.query(Company).filter(Company.invite_code == invite_code).first()
    return CompanyRead.model_validate(company) if company else None


def get_by_vk_id(db: Session, vk_user_id: int) -> CompanyRead | None:
    """Возвращает УК по VK-ID её контроллера или None, если не найдена.

    Используется ботом для маршрутизации: если отправитель — контроллер,
    его vk_user_id хранится в company.vk_user_id.
    """
    company = db.query(Company).filter(Company.vk_user_id == vk_user_id).first()
    return CompanyRead.model_validate(company) if company else None


def set_status(db: Session, company_id: int, status: int) -> CompanyRead | None:
    """Устанавливает статус УК (0=active, 1=pending, 2=denied).

    Вызывается администратором при одобрении или отклонении заявки.
    Возвращает обновлённую запись или None, если УК не найдена.
    """
    company = db.get(Company, company_id)
    if company is None:
        return None
    company.status = status
    db.commit()
    db.refresh(company)
    return CompanyRead.model_validate(company)


def list_pending(db: Session) -> list[CompanyRead]:
    """Возвращает все УК со статусом pending (1), отсортированные по дате создания.

    Используется администратором для просмотра очереди заявок на регистрацию.
    """
    companies = (
        db.query(Company)
        .filter(Company.status == 1)
        .order_by(Company.created_at)
        .all()
    )
    return [CompanyRead.model_validate(c) for c in companies]


def list_active_vk_ids(db: Session) -> list[int]:
    """Возвращает список VK-ID контроллеров всех активных УК.

    Используется для рассылки уведомлений всем пользователям системы.
    NULL-значения (отозвавшие согласие) исключаются.

    Args:
        db: Сессия SQLAlchemy.
    """
    rows = (
        db.query(Company.vk_user_id)
        .filter(Company.status == 0, Company.vk_user_id.isnot(None))
        .all()
    )
    return [r[0] for r in rows]


def withdraw_consent(db: Session, company_id: int) -> CompanyRead | None:
    """Затирает ПДн контроллера УК при отзыве согласия по email.

    Устанавливает статус denied, обнуляет идентифицирующие поля.
    Запись сохраняется — на неё ссылаются отчёты и дворники.
    Вызывается вручную из консоли при получении письма-отзыва.

    Args:
        db: Сессия SQLAlchemy.
        company_id: Первичный ключ УК.

    Returns:
        CompanyRead: Обновлённая запись или None, если УК не найдена.
    """
    company = db.get(Company, company_id)
    if company is None:
        return None
    today = datetime.now(tz=timezone.utc).strftime("%d.%m.%Y")
    company.name = f"Согласие отозвано {today}"
    company.phone = None
    company.vk_user_id = None
    company.consent_given_at = None
    company.consent_version = None
    company.status = 2  # denied
    db.commit()
    db.refresh(company)
    return CompanyRead.model_validate(company)


def count_total_active(db: Session) -> int:
    """Возвращает общее количество активных УК (status=0).

    Args:
        db: Сессия SQLAlchemy.
    """
    return db.query(Company).filter(Company.status == 0).count()


def count_new_since(db: Session, since: datetime) -> int:
    """Возвращает количество УК, созданных с момента since (все статусы).

    Args:
        db: Сессия SQLAlchemy.
        since: Начало периода (UTC).
    """
    return db.query(Company).filter(Company.created_at >= since).count()
