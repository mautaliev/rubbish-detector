"""CRUD-операции для управляющих компаний (УК)."""

from sqlalchemy.orm import Session

from ..models import Company
from ..schemas import CompanyCreate, CompanyRead


def create(db: Session, data: CompanyCreate) -> CompanyRead:
    """Создаёт новую УК и возвращает её из БД (с заполненными id и created_at)."""
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
