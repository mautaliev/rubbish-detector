"""CRUD-операции для дворников."""

from datetime import datetime, timezone

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ..models import Cleaner
from ..schemas import CleanerRead


def register(
    db: Session,
    vk_user_id: int,
    full_name: str,
    company_id: int,
    consent_given_at: datetime | None = None,
    consent_version: str | None = None,
) -> CleanerRead:
    """Регистрирует дворника или обновляет его данные, если он уже существует.

    Реализует upsert по уникальному полю vk_user_id:
    - если дворника с таким vk_user_id нет — создаёт новую запись;
    - если есть — обновляет full_name, company_id и факт согласия (дворник мог сменить УК).

    Сценарий использования: дворник отправляет боту invite_code УК,
    бот вызывает register() с найденным company_id.

    Args:
        db: Сессия SQLAlchemy.
        vk_user_id: VK-ID дворника.
        full_name: ФИО из профиля VK.
        company_id: ID компании, к которой привязывается дворник.
        consent_given_at: UTC-момент нажатия «Принимаю».
        consent_version: Версия текста согласия (напр. "v1").
    """
    stmt = (
        insert(Cleaner)
        .values(
            vk_user_id=vk_user_id,
            full_name=full_name,
            company_id=company_id,
            consent_given_at=consent_given_at,
            consent_version=consent_version,
        )
        .on_conflict_do_update(
            index_elements=["vk_user_id"],
            set_={
                "full_name": full_name,
                "company_id": company_id,
                "consent_given_at": consent_given_at,
                "consent_version": consent_version,
            },
        )
        .returning(Cleaner)
    )
    result = db.execute(stmt)
    db.commit()
    cleaner = result.scalars().one()
    return CleanerRead.model_validate(cleaner)


def get_by_vk_id(db: Session, vk_user_id: int) -> CleanerRead | None:
    """Возвращает дворника по его VK-ID или None, если не зарегистрирован.

    Основная точка входа для бота: каждое входящее сообщение идентифицируется
    по vk_user_id отправителя.
    """
    cleaner = db.query(Cleaner).filter(Cleaner.vk_user_id == vk_user_id).first()
    return CleanerRead.model_validate(cleaner) if cleaner else None


def list_all_vk_ids(db: Session) -> list[int]:
    """Возвращает список VK-ID всех зарегистрированных дворников.

    Используется для рассылки уведомлений всем пользователям системы.
    """
    rows = db.query(Cleaner.vk_user_id).all()
    return [r[0] for r in rows]


def count_total(db: Session) -> int:
    """Возвращает общее количество зарегистрированных дворников.

    Args:
        db: Сессия SQLAlchemy.
    """
    return db.query(Cleaner).count()


def count_new_since(db: Session, since: datetime) -> int:
    """Возвращает количество дворников, зарегистрированных с момента since.

    Args:
        db: Сессия SQLAlchemy.
        since: Начало периода (UTC).
    """
    return db.query(Cleaner).filter(Cleaner.created_at >= since).count()


def withdraw_consent(db: Session, vk_user_id: int) -> CleanerRead | None:
    """Отзывает согласие дворника: затирает ПДн, обнуляет vk_user_id.

    После вызова запись остаётся в БД для сохранения истории отчётов,
    но идентифицировать дворника по vk_user_id более невозможно.

    Args:
        db: Сессия SQLAlchemy.
        vk_user_id: VK-ID дворника, отзывающего согласие.

    Returns:
        CleanerRead с обновлёнными данными или None, если дворник не найден.
    """
    cleaner = db.query(Cleaner).filter(Cleaner.vk_user_id == vk_user_id).first()
    if cleaner is None:
        return None
    date_str = datetime.now(tz=timezone.utc).strftime("%d.%m.%Y")
    cleaner.full_name = f"Согласие на хранение ПД отозвано {date_str}"
    cleaner.vk_user_id = None
    cleaner.consent_given_at = None
    cleaner.consent_version = None
    db.commit()
    db.refresh(cleaner)
    return CleanerRead.model_validate(cleaner)
