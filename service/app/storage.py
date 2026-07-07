import datetime
import io
import os
import uuid

import aioboto3
from PIL import Image

_session = aioboto3.Session()


def is_configured() -> bool:
    """Возвращает True, если переменные окружения S3 заданы и хранилище доступно."""
    return bool(os.environ.get("S3_ENDPOINT_URL") and os.environ.get("S3_BUCKET"))


def _client():
    """Создаёт aioboto3 S3-клиент из переменных окружения."""
    return _session.client(
        "s3",
        endpoint_url=os.environ["S3_ENDPOINT_URL"],
        aws_access_key_id=os.environ["S3_ACCESS_KEY"],
        aws_secret_access_key=os.environ["S3_SECRET_KEY"],
        region_name=os.environ.get("S3_REGION", "ru-1"),
    )


def _prefix(company_id: int | None) -> str:
    """Возвращает префикс S3-ключа: id компании или 'unauthorized'.

    Args:
        company_id: id управляющей компании или None для неавторизованного запроса.
    """
    return str(company_id) if company_id is not None else "unauthorized"


def _to_jpeg(img: Image.Image) -> bytes:
    """Кодирует PIL-изображение в JPEG с качеством 92.

    Args:
        img: PIL-изображение для кодирования.
    """
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92)
    return buf.getvalue()


async def save_pair(
    company_id: int | None,
    original: bytes,
    detected: bytes,
    ext: str = "jpg",
) -> dict:
    """Сохраняет пару original/detected в S3. Возвращает file_id и S3-ключи.

    Args:
        company_id: id управляющей компании или None для неавторизованного запроса.
        original: байты исходного изображения.
        detected: байты размеченного изображения.
        ext: расширение файла (по умолчанию 'jpg').
    """
    prefix = _prefix(company_id)
    day = datetime.date.today().isoformat()
    file_id = uuid.uuid4().hex
    keys = {
        "original": f"{prefix}/original/{day}/{file_id}.{ext}",
        "detected": f"{prefix}/detected/{day}/{file_id}.{ext}",
    }
    bucket = os.environ["S3_BUCKET"]
    async with _client() as s3:
        await s3.put_object(
            Bucket=bucket, Key=keys["original"], Body=original, ContentType="image/jpeg"
        )
        await s3.put_object(
            Bucket=bucket, Key=keys["detected"], Body=detected, ContentType="image/jpeg"
        )
    return {"id": file_id, "keys": keys}


async def download(key: str) -> bytes:
    """Скачивает объект из S3 по ключу и возвращает его содержимое.

    Args:
        key: S3-ключ объекта (например, '100/original/2026-06-20/3f9ac1d2.jpg').

    Returns:
        bytes: Содержимое объекта.
    """
    bucket = os.environ["S3_BUCKET"]
    async with _client() as s3:
        response = await s3.get_object(Bucket=bucket, Key=key)
        return await response["Body"].read()


async def save_agreement(company_id: int, file_bytes: bytes, file_name: str, content_type: str = "application/octet-stream") -> str:
    """[LEGACY] Сохраняет файл согласия на ПД в S3 по пути agreements/{company_id}/{file_name}.

    Не вызывается начиная с миграции на схему «оператор» (v2 согласия, миграция 0005).
    Оставлена для истории; существующие объекты в S3 под префиксом agreements/ не удаляются.

    Args:
        company_id: ID управляющей компании.
        file_bytes: Содержимое файла.
        file_name: Имя файла (будет использовано как последняя часть ключа).
        content_type: MIME-тип файла.

    Returns:
        str: S3-ключ сохранённого файла.
    """
    key = f"agreements/{company_id}/{file_name}"
    bucket = os.environ["S3_BUCKET"]
    async with _client() as s3:
        await s3.put_object(Bucket=bucket, Key=key, Body=file_bytes, ContentType=content_type)
    return key


async def get_presigned_url(key: str, expires: int = 3600) -> str:
    """Возвращает presigned URL на объект, действительный `expires` секунд.

    Args:
        key: S3-ключ объекта (например, '100/detected/2026-06-20/3f9ac1d2.jpg').
        expires: срок жизни ссылки в секундах (по умолчанию 3600 — 1 час).
    """
    async with _client() as s3:
        return await s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": os.environ["S3_BUCKET"], "Key": key},
            ExpiresIn=expires,
        )
