import base64
import io

import pytest
from PIL import Image


def _make_rgb_image(width: int = 20, height: int = 20) -> Image.Image:
    """Создаёт небольшое RGB-изображение заданного размера для использования в тестах."""
    img = Image.new("RGB", (width, height), color=(100, 150, 200))
    return img


def _image_to_base64(img: Image.Image) -> str:
    """Сохраняет PIL-изображение в формат PNG и возвращает его как строку base64."""
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def _image_to_data_url(img: Image.Image) -> str:
    """Возвращает изображение в виде data URL с префиксом 'data:image/png;base64,'."""
    return "data:image/png;base64," + _image_to_base64(img)


@pytest.fixture()
def sample_image() -> Image.Image:
    """Фикстура: возвращает небольшое RGB PIL-изображение 20×20 пикселей."""
    return _make_rgb_image()


@pytest.fixture()
def sample_base64(sample_image) -> str:
    """Фикстура: возвращает sample_image, закодированное в строку base64 (PNG)."""
    return _image_to_base64(sample_image)


@pytest.fixture()
def sample_data_url(sample_image) -> str:
    """Фикстура: возвращает sample_image в виде data URL (PNG, base64)."""
    return _image_to_data_url(sample_image)


@pytest.fixture()
def sample_bytes(sample_image) -> bytes:
    """Фикстура: возвращает sample_image в виде сырых байт PNG."""
    buf = io.BytesIO()
    sample_image.save(buf, format="PNG")
    return buf.getvalue()
