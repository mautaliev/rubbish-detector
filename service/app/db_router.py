from fastapi import APIRouter, Depends, Form, HTTPException
from sqlalchemy.orm import Session

from ..db.crud import cleaner as cleaner_crud
from ..db.crud import company as company_crud
from ..db.crud import report as report_crud
from ..db.engine import get_db
from ..db.models import Cleaner, Company, Report
from ..db.schemas import CleanerRead, CompanyCreate, CompanyRead, ReportCreate, ReportRead

router = APIRouter(prefix="/api/db", tags=["database"])


@router.post("/companies")
def create_company(data: CompanyCreate, db: Session = Depends(get_db)):
    try:
        return company_crud.create(db, data)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/companies")
def list_companies(db: Session = Depends(get_db)):
    rows = db.query(Company).order_by(Company.id).all()
    return [CompanyRead.model_validate(r) for r in rows]


@router.post("/cleaners")
def register_cleaner(
    vk_user_id: int = Form(...),
    full_name: str = Form(...),
    company_id: int = Form(...),
    db: Session = Depends(get_db),
):
    try:
        return cleaner_crud.register(db, vk_user_id=vk_user_id, full_name=full_name, company_id=company_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/cleaners")
def list_cleaners(db: Session = Depends(get_db)):
    rows = db.query(Cleaner).order_by(Cleaner.id).all()
    return [CleanerRead.model_validate(r) for r in rows]


@router.post("/reports")
def create_report(data: ReportCreate, db: Session = Depends(get_db)):
    try:
        return report_crud.create_report(db, data)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/reports")
def list_reports(
    company_id: int | None = None,
    cleaner_id: int | None = None,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    if cleaner_id is not None:
        return report_crud.list_by_cleaner(db, cleaner_id=cleaner_id, limit=limit)
    if company_id is not None:
        return report_crud.list_by_company(db, company_id=company_id, limit=limit)
    rows = db.query(Report).order_by(Report.created_at.desc()).limit(limit).all()
    return [ReportRead.model_validate(r) for r in rows]
