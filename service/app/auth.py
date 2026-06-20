import os

from fastapi import HTTPException, status


def require_local() -> None:
    """FastAPI-зависимость: возвращает 404 в продакшне или без явного TESTLAB_ENABLED=1.

    Два независимых барьера:
    - ENVIRONMENT=production всегда блокирует, даже если TESTLAB_ENABLED=1 случайно задан.
    - Отсутствие TESTLAB_ENABLED=1 блокирует в любом окружении.

    В локальной разработке установи TESTLAB_ENABLED=1 и ENVIRONMENT=development в .env.
    """
    if os.environ.get("ENVIRONMENT", "") == "production":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if os.environ.get("TESTLAB_ENABLED", "") != "1":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
