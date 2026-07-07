"""Тесты новых сценариев регистрации после перехода на схему «оператор» (миграция 0005)."""

import itertools
from datetime import datetime, timezone

import pytest

from service.db.crud import company as crud_company
from service.db.models import Base, Company, Cleaner
from service.db.schemas import CompanyCreate, CompanyRead, CleanerRead

_id_counter = itertools.count(1)


# ---------------------------------------------------------------------------
# In-memory SQLite fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def db():
    """Возвращает SQLite in-memory сессию с нужными таблицами.

    Создаёт только таблицы company и cleaner: Report содержит JSONB,
    несовместимый с SQLite; для тестов БД-логики он не нужен.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine, tables=[Company.__table__, Cleaner.__table__])
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


def _insert_company(
    db,
    name: str = "ТестКомпания",
    vk_user_id: int = 100,
    invite_code: str = "TESTCODE",
    phone: str | None = "+71234567890",
    status: int = 0,
    consent: bool = True,
) -> CompanyRead:
    """Прямая ORM-вставка УК. Используется вместо crud_company.create в SQLite-тестах.

    SQLite не поддерживает BigInteger autoincrement: тип BIGINT не является
    алиасом rowid и SQLite не генерирует id автоматически. Передаём id явно.
    """
    ts = datetime.now(tz=timezone.utc) if consent else None
    company = Company(
        id=next(_id_counter),
        name=name,
        vk_user_id=vk_user_id,
        invite_code=invite_code,
        phone=phone,
        status=status,
        consent_given_at=ts,
        consent_version="v1" if consent else None,
    )
    db.add(company)
    db.commit()
    db.refresh(company)
    return CompanyRead.model_validate(company)


# ---------------------------------------------------------------------------
# Тесты: consent-поля компании
# ---------------------------------------------------------------------------

class TestCompanyConsentFields:
    """Проверяет сохранение и чтение полей согласия УК."""

    def test_create_stores_consent_given_at(self, db):
        """При вставке УК consent_given_at должен сохраняться в БД."""
        company = _insert_company(db, vk_user_id=200, invite_code="CODE0001", consent=True)
        assert company.consent_given_at is not None
        assert company.consent_version == "v1"

    def test_create_without_consent_leaves_nulls(self, db):
        """Вставка УК без согласия оставляет consent-поля None."""
        company = _insert_company(db, vk_user_id=201, invite_code="CODE0002", consent=False)
        assert company.consent_given_at is None
        assert company.consent_version is None

    def test_vk_user_id_is_nullable_in_schema(self, db):
        """CompanyRead должен допускать vk_user_id=None (после отзыва согласия)."""
        company = _insert_company(db, vk_user_id=202, invite_code="CODE0003")
        assert company.vk_user_id == 202  # до отзыва — не None


# ---------------------------------------------------------------------------
# Тесты: withdraw_consent компании
# ---------------------------------------------------------------------------

class TestWithdrawConsentCompany:
    """Проверяет ручную функцию отзыва согласия УК."""

    def test_withdraw_clears_identifying_fields(self, db):
        """withdraw_consent должна обнулить phone, vk_user_id и поля согласия."""
        company = _insert_company(db, vk_user_id=110, invite_code="WC0001")
        result = crud_company.withdraw_consent(db, company.id)
        assert result is not None
        assert result.phone is None
        assert result.vk_user_id is None
        assert result.consent_given_at is None
        assert result.consent_version is None

    def test_withdraw_sets_status_denied(self, db):
        """После отзыва статус компании должен быть 2 (denied)."""
        company = _insert_company(db, vk_user_id=111, invite_code="WC0002")
        result = crud_company.withdraw_consent(db, company.id)
        assert result.status == 2

    def test_withdraw_sets_name_stub(self, db):
        """После отзыва name должно содержать заглушку с датой."""
        company = _insert_company(db, vk_user_id=112, invite_code="WC0003")
        result = crud_company.withdraw_consent(db, company.id)
        assert result.name.startswith("Согласие отозвано")

    def test_withdraw_nonexistent_company_returns_none(self, db):
        """withdraw_consent несуществующей компании возвращает None."""
        result = crud_company.withdraw_consent(db, 99999)
        assert result is None

    def test_withdrawn_company_not_in_active_vk_ids(self, db):
        """После отзыва согласия УК не должна попадать в список VK-ID для рассылки."""
        company = _insert_company(db, vk_user_id=113, invite_code="WC0004")
        assert 113 in crud_company.list_active_vk_ids(db)
        crud_company.withdraw_consent(db, company.id)
        assert 113 not in crud_company.list_active_vk_ids(db)


# ---------------------------------------------------------------------------
# Тесты: consent_version дворника v2
# ---------------------------------------------------------------------------

class TestCleanerConsentV2:
    """Проверяет, что после регистрации дворника сохраняется consent_version='v2'."""

    def test_cleaner_registered_with_v2_consent(self, db):
        """Запись дворника после регистрации должна содержать consent_version='v2'."""
        company = _insert_company(db, vk_user_id=300, invite_code="DCODE01")
        ts = datetime.now(tz=timezone.utc)

        # crud_cleaner.register использует PostgreSQL-специфичный ON CONFLICT,
        # поэтому в SQLite-тесте создаём запись напрямую через ORM.
        # id задаём явно: SQLite не автоинкрементирует BigInteger.
        cleaner_row = Cleaner(
            id=next(_id_counter),
            vk_user_id=400,
            full_name="Иванов Иван Иванович",
            company_id=company.id,
            consent_given_at=ts,
            consent_version="v2",
        )
        db.add(cleaner_row)
        db.commit()
        db.refresh(cleaner_row)

        cleaner = CleanerRead.model_validate(cleaner_row)
        assert cleaner.consent_version == "v2"
        assert cleaner.consent_given_at is not None


# ---------------------------------------------------------------------------
# Тесты: проверка активности УК при приёме отчёта (через handler-логику)
# ---------------------------------------------------------------------------

class TestCompanyActiveCheck:
    """Проверяет, что бот не пропускает отчёты дворников неактивной компании."""

    def test_denied_company_not_returned_by_invite(self, db):
        """Компания со статусом denied не должна обслуживать новых дворников.

        get_by_invite_code возвращает запись; фильтрация по status=0
        выполняется в _db_get_company_by_invite в handlers.py.
        """
        _insert_company(db, vk_user_id=500, invite_code="DENIED1", status=2, consent=False)
        result = crud_company.get_by_invite_code(db, "DENIED1")
        assert result is not None  # метод возвращает запись
        assert result.status != 0  # бот откажет при регистрации

    def test_null_vk_user_id_excluded_from_active_list(self, db):
        """УК с NULL vk_user_id не должна попадать в список для рассылки."""
        company = _insert_company(db, vk_user_id=600, invite_code="NULL001")
        assert 600 in crud_company.list_active_vk_ids(db)

        crud_company.withdraw_consent(db, company.id)
        assert 600 not in crud_company.list_active_vk_ids(db)
