import os

from fastapi import HTTPException, status


def require_local() -> None:
    """FastAPI-зависимость: возвращает 404 везде, кроме явно разрешённого dev-окружения.

    Блокирует по умолчанию (fail-closed): если ENVIRONMENT не задан или не равен
    "development" — доступ закрыт, даже если TESTLAB_ENABLED=1 случайно выставлен.

    В локальной разработке установи ENVIRONMENT=development и TESTLAB_ENABLED=1.
    """
    if os.environ.get("ENVIRONMENT", "production") != "development":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if os.environ.get("TESTLAB_ENABLED", "") != "1":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
