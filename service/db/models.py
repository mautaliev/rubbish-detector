import enum
import uuid

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Enum,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import DeclarativeBase, relationship


class ModelVersion(enum.Enum):
    """Версия модели детекции, которой обработан отчёт.

    single_class — одноклассовая модель: только факт наличия мусора.
    multi_class  — многоклассовая модель: разбивка по видам мусора.
    """

    single_class = "single_class"
    multi_class = "multi_class"


class Base(DeclarativeBase):
    pass


class Company(Base):
    """Управляющая компания (УК), она же контроллер.

    Является корневой сущностью: к УК привязаны дворники и их отчёты.
    VK-бот отправляет уведомления о грязных отчётах на vk_user_id УК.
    """

    __tablename__ = "company"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(Text, nullable=False)  # название УК
    vk_user_id = Column(BigInteger, nullable=False)  # VK-ID контроллера для уведомлений
    invite_code = Column(Text, nullable=False, unique=True)  # код регистрации дворников
    default_model = Column(
        Enum(ModelVersion, name="model_version"),
        nullable=False,
        default=ModelVersion.single_class,
    )  # модель по умолчанию для новых отчётов этой УК
    phone = Column(Text, nullable=True)  # контактный телефон УК
    status = Column(SmallInteger, nullable=False, server_default="1")  # 0=active, 1=pending, 2=denied
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    cleaners = relationship("Cleaner", back_populates="company")
    reports = relationship("Report", back_populates="company")


class Cleaner(Base):
    """Дворник, привязанный к одной УК.

    Идентифицируется по vk_user_id — именно по нему бот определяет
    отправителя при входящем сообщении.
    """

    __tablename__ = "cleaner"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    company_id = Column(BigInteger, ForeignKey("company.id"), nullable=False)  # FK → company
    full_name = Column(Text, nullable=False)
    vk_user_id = Column(BigInteger, nullable=False, unique=True)  # уникальный VK-ID дворника
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    company = relationship("Company", back_populates="cleaners")
    reports = relationship("Report", back_populates="cleaner")


class Report(Base):
    """Отчёт дворника: результат детекции по одному или нескольким фото.

    Содержит как исходные фото (ключи в S3), так и агрегированный итог
    (is_clean, photos_count, objects_count). model_version фиксируется
    на момент создания — изменение default_model у УК не влияет на
    уже созданные отчёты.
    """

    __tablename__ = "report"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cleaner_id = Column(BigInteger, ForeignKey("cleaner.id"), nullable=False)  # FK → cleaner
    company_id = Column(BigInteger, ForeignKey("company.id"), nullable=False)  # денормализация для быстрых выборок по УК
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    comment = Column(Text, nullable=True)  # текст сообщения дворника, если был
    model_version = Column(Enum(ModelVersion, name="model_version"), nullable=False)  # зафиксированная версия модели
    photos = Column(JSONB, nullable=False, default=list)  # массив PhotoResult (см. schemas.py)
    is_clean = Column(Boolean, nullable=False)  # true, если все фото чистые
    photos_count = Column(Integer, nullable=False)  # количество фото в отчёте
    objects_count = Column(Integer, nullable=False)  # суммарное число найденных объектов
    notified_at = Column(TIMESTAMP(timezone=True), nullable=True)  # время уведомления контроллера; null — не отправлялось

    cleaner = relationship("Cleaner", back_populates="reports")
    company = relationship("Company", back_populates="reports")


# Составные индексы для выборок «все отчёты УК/дворника, отсортированные по дате»
Index("idx_report_company_created", Report.company_id, Report.created_at)
Index("idx_report_cleaner_created", Report.cleaner_id, Report.created_at)
