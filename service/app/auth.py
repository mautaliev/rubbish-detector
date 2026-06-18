import os

from fastapi import HTTPException, status


def require_local() -> None:
    """FastAPI-зависимость: возвращает 404 если TESTLAB_ENABLED != '1'.

    Блокирует доступ к /testlab и /api/db/* в продакшне.
    В локальной разработке установи TESTLAB_ENABLED=1 в .env.
    """
    if os.environ.get("TESTLAB_ENABLED", "") != "1":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
