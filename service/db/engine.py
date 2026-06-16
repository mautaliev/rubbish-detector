import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.environ["DATABASE_URL"]

# pool_pre_ping=True: перед каждым использованием соединения проверяет,
# что оно живо; защищает от ошибок после простоя или перезапуска БД
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_db():
    """Генератор сессии для dependency injection (FastAPI / прямой вызов).

    Гарантирует закрытие сессии даже при исключении.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
