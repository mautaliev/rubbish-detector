import logging

from fastapi import APIRouter, Depends, Form, HTTPException
from sqlalchemy.orm import Session

from ..db.crud import cleaner as cleaner_crud
from ..db.crud import company as company_crud
from ..db.crud import report as report_crud
from ..db.engine import get_db
from ..db.models import Cleaner, Company, Report
from ..db.schemas import CleanerRead, CompanyCreate, CompanyRead, ReportCreate, ReportRead
from .auth import require_local

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/db", tags=["database"], dependencies=[Depends(require_local)])


@router.post("/companies")
def create_company(data: CompanyCreate, db: Session = Depends(get_db)):
    """Создаёт новую управляющую компанию.

    Args:
        data: Данные компании (название, vk_user_id контроллера, invite-код, модель по умолчанию).
        db: Сессия базы данных.

    Returns:
        CompanyRead: Созданная запись компании.
    """
    try:
        return company_crud.create(db, data)
    except Exception as exc:
        logger.error("create_company error: %s", exc)
        raise HTTPException(status_code=400, detail="Could not create company") from exc


@router.get("/companies")
def list_companies(db: Session = Depends(get_db)):
    """Возвращает список всех управляющих компаний, отсортированных по id.

    Args:
        db: Сессия базы данных.

    Returns:
        list[CompanyRead]: Список компаний.
    """
    rows = db.query(Company).order_by(Company.id).all()
    return [CompanyRead.model_validate(r) for r in rows]


@router.post("/cleaners")
def register_cleaner(
    vk_user_id: int = Form(...),
    full_name: str = Form(...),
    company_id: int = Form(...),
    db: Session = Depends(get_db),
):
    """Регистрирует нового дворника и привязывает его к управляющей компании.

    Args:
        vk_user_id: VK ID дворника.
        full_name: Полное имя дворника.
        company_id: ID управляющей компании.
        db: Сессия базы данных.

    Returns:
        CleanerRead: Созданная запись дворника.
    """
    try:
        return cleaner_crud.register(db, vk_user_id=vk_user_id, full_name=full_name, company_id=company_id)
    except Exception as exc:
        logger.error("register_cleaner error: %s", exc)
        raise HTTPException(status_code=400, detail="Could not register cleaner") from exc


@router.get("/cleaners")
def list_cleaners(db: Session = Depends(get_db)):
    """Возвращает список всех зарегистрированных дворников, отсортированных по id.

    Args:
        db: Сессия базы данных.

    Returns:
        list[CleanerRead]: Список дворников.
    """
    rows = db.query(Cleaner).order_by(Cleaner.id).all()
    return [CleanerRead.model_validate(r) for r in rows]


@router.post("/reports")
def create_report(data: ReportCreate, db: Session = Depends(get_db)):
    """Создаёт новый отчёт об уборке с привязанными фотографиями.

    Args:
        data: Данные отчёта (cleaner_id, company_id, модель, фотографии, комментарий).
        db: Сессия базы данных.

    Returns:
        ReportRead: Созданная запись отчёта.
    """
    try:
        return report_crud.create_report(db, data)
    except Exception as exc:
        logger.error("create_report error: %s", exc)
        raise HTTPException(status_code=400, detail="Could not create report") from exc


@router.get("/reports")
def list_reports(
    company_id: int | None = None,
    cleaner_id: int | None = None,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    """Возвращает список отчётов с опциональной фильтрацией по компании или дворнику.

    Args:
        company_id: Если задан — возвращает только отчёты этой компании.
        cleaner_id: Если задан — возвращает только отчёты этого дворника (приоритет над company_id).
        limit: Максимальное количество записей в ответе (по умолчанию 50).
        db: Сессия базы данных.

    Returns:
        list[ReportRead]: Список отчётов, отсортированных по дате создания (новые первыми).
    """
    if cleaner_id is not None:
        return report_crud.list_by_cleaner(db, cleaner_id=cleaner_id, limit=limit)
    if company_id is not None:
        return report_crud.list_by_company(db, company_id=company_id, limit=limit)
    rows = db.query(Report).order_by(Report.created_at.desc()).limit(limit).all()
    return [ReportRead.model_validate(r) for r in rows]
