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
    """Возвращает префикс S3-ключа: id компании или 'unauthorized'."""
    return str(company_id) if company_id is not None else "unauthorized"


def _to_jpeg(img: Image.Image) -> bytes:
    """Кодирует PIL-изображение в JPEG с качеством 92."""
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92)
    return buf.getvalue()


async def save_pair(
    company_id: int | None,
    original: bytes,
    detected: bytes,
    ext: str = "jpg",
) -> dict:
    """Сохраняет пару original/detected в S3. Возвращает file_id и S3-ключи."""
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


async def get_presigned_url(key: str, expires: int = 3600) -> str:
    """Возвращает presigned URL на объект, действительный `expires` секунд."""
    async with _client() as s3:
        return await s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": os.environ["S3_BUCKET"], "Key": key},
            ExpiresIn=expires,
        )
