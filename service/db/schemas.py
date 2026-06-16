"""Pydantic-схемы для CRUD-фасада.

Разделены на пары *Create / *Read:
- *Create — входные данные при записи в БД;
- *Read   — данные, возвращаемые из БД (включая серверные поля: id, created_at).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from .models import ModelVersion


class CompanyCreate(BaseModel):
    """Данные для создания управляющей компании."""

    name: str
    vk_user_id: int  # VK-ID контроллера для уведомлений
    invite_code: str  # уникальный код регистрации дворников
    default_model: ModelVersion = ModelVersion.single_class


class CompanyRead(BaseModel):
    """Управляющая компания, прочитанная из БД."""

    id: int
    name: str
    vk_user_id: int
    invite_code: str
    default_model: ModelVersion
    created_at: datetime

    model_config = {"from_attributes": True}


class CleanerCreate(BaseModel):
    """Данные для регистрации дворника (company_id передаётся отдельно в crud.cleaner.register)."""

    vk_user_id: int
    full_name: str


class CleanerRead(BaseModel):
    """Дворник, прочитанный из БД."""

    id: int
    company_id: int
    full_name: str
    vk_user_id: int
    created_at: datetime

    model_config = {"from_attributes": True}


class PhotoResult(BaseModel):
    """Результат детекции по одному фото (элемент массива report.photos).

    original_key / detected_key — ключи объектов в S3.
    classes — заполняется только для multi_class модели; для single_class — пустой dict.
    """

    original_key: str
    detected_key: str
    total_objects: int
    classes: dict[str, int]
    is_clean: bool


class ReportCreate(BaseModel):
    """Данные для создания отчёта.

    Агрегаты (photos_count, objects_count, is_clean) вычисляются
    автоматически в crud.report.create_report по переданному списку photos.
    """

    cleaner_id: int
    company_id: int
    model_version: ModelVersion  # фиксируется из company.default_model на момент создания
    photos: list[PhotoResult]
    comment: str | None = None


class ReportRead(BaseModel):
    """Отчёт, прочитанный из БД."""

    id: uuid.UUID
    cleaner_id: int
    company_id: int
    created_at: datetime
    comment: str | None
    model_version: ModelVersion
    photos: list[Any]  # JSONB — возвращается как list[dict]
    is_clean: bool
    photos_count: int
    objects_count: int
    notified_at: datetime | None  # None — уведомление не отправлялось

    model_config = {"from_attributes": True}
