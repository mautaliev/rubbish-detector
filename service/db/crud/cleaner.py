"""CRUD-операции для дворников."""

from datetime import datetime

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ..models import Cleaner
from ..schemas import CleanerRead


def register(db: Session, vk_user_id: int, full_name: str, company_id: int) -> CleanerRead:
    """Регистрирует дворника или обновляет его данные, если он уже существует.

    Реализует upsert по уникальному полю vk_user_id:
    - если дворника с таким vk_user_id нет — создаёт новую запись;
    - если есть — обновляет full_name и company_id (дворник мог сменить УК).

    Сценарий использования: дворник отправляет боту invite_code УК,
    бот вызывает register() с найденным company_id.
    """
    stmt = (
        insert(Cleaner)
        .values(vk_user_id=vk_user_id, full_name=full_name, company_id=company_id)
        .on_conflict_do_update(
            index_elements=["vk_user_id"],
            set_={"full_name": full_name, "company_id": company_id},
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
