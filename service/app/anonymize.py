"""
anonymize.py — обезличивание изображений перед сохранением в хранилище.

Блюрит:
  * лица   — детектор CenterFace из пакета deface (обучен на WIDER FACE);
  * номера — YOLO-модель, веса лежат в репозитории в папке models/.

Используется пикселизация (а не лёгкое размытие): она необратима,
по ней нельзя восстановить лицо или прочитать номер OCR-ом.

Установка зависимостей:
    pip install deface
"""

import os
import threading
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
from deface.centerface import CenterFace
from ultralytics import YOLO

# OpenCV DNN is not thread-safe: serialize all inference calls
_INFERENCE_LOCK = threading.Lock()

# Папка models/ в корне репозитория
_MODELS_DIR = Path(__file__).resolve().parents[2] / "models"

CENTERFACE_PATH = os.getenv("CENTERFACE_PATH", str(_MODELS_DIR / "centerface.onnx"))
PLATE_PATH = os.getenv("PLATE_PATH", str(_MODELS_DIR / "license-plate-finetune-v1n.pt"))
FACE_THRESH = float(os.getenv("FACE_THRESH", "0.2"))
PLATE_CONF = float(os.getenv("PLATE_CONF", "0.25"))
PAD = float(os.getenv("ANON_PAD", "0.15"))


@lru_cache(maxsize=1)
def _face_detector() -> CenterFace:
    """Ленивая singleton-загрузка детектора лиц (один раз на процесс)."""
    return CenterFace(CENTERFACE_PATH)


@lru_cache(maxsize=1)
def _plate_detector() -> YOLO:
    """Ленивая singleton-загрузка YOLO-модели номеров."""
    return YOLO(PLATE_PATH)


def _pixelate(img: np.ndarray, x1, y1, x2, y2, blocks: int = 8) -> None:
    """Необратимая пикселизация прямоугольной области (in-place).

    Args:
        img: BGR-изображение.
        x1, y1, x2, y2: Координаты бокса.
        blocks: Размер сетки пикселизации.
    """
    h, w = img.shape[:2]
    bw, bh = (x2 - x1), (y2 - y1)
    x1 = max(0, int(x1 - bw * PAD))
    y1 = max(0, int(y1 - bh * PAD))
    x2 = min(w, int(x2 + bw * PAD))
    y2 = min(h, int(y2 + bh * PAD))
    if x2 <= x1 or y2 <= y1:
        return
    roi = img[y1:y2, x1:x2]
    rh, rw = roi.shape[:2]
    small = cv2.resize(roi, (blocks, blocks), interpolation=cv2.INTER_LINEAR)
    img[y1:y2, x1:x2] = cv2.resize(small, (rw, rh), interpolation=cv2.INTER_NEAREST)


def anonymize_bgr(img: np.ndarray) -> np.ndarray:
    """Блюрит все лица и номера на изображении (формат BGR, как у cv2).

    Меняет img на месте и возвращает его же.

    Args:
        img: BGR-изображение.

    Returns:
        np.ndarray: То же изображение с пикселизованными лицами и номерами.
    """
    with _INFERENCE_LOCK:
        dets, _ = _face_detector()(img, threshold=FACE_THRESH)
        for x1, y1, x2, y2, _score in dets:
            _pixelate(img, x1, y1, x2, y2, blocks=8)

        results = _plate_detector()(img, conf=PLATE_CONF, verbose=False)
        for box in results[0].boxes.xyxy.cpu().numpy():
            x1, y1, x2, y2 = box[:4]
            _pixelate(img, x1, y1, x2, y2, blocks=6)

    return img


def anonymize_bytes(data: bytes, ext: str = "jpg") -> bytes:
    """Принимает байты изображения, возвращает байты обезличенного.

    Args:
        data: Байты исходного изображения.
        ext: Расширение для кодирования результата (jpg, png и т.д.).

    Returns:
        bytes: Байты обезличенного изображения.

    Raises:
        ValueError: Если изображение не удалось декодировать или закодировать.
    """
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("не удалось декодировать изображение")

    anonymize_bgr(img)

    ok, buf = cv2.imencode(f".{ext}", img)
    if not ok:
        raise ValueError("не удалось закодировать изображение")
    return buf.tobytes()


def warmup() -> None:
    """Прогрев моделей на старте приложения, чтобы первый запрос не тормозил."""
    _face_detector()
    _plate_detector()


if __name__ == "__main__":
    import sys
    src, dst = sys.argv[1], sys.argv[2]
    with open(src, "rb") as f:
        result = anonymize_bytes(f.read(), ext=dst.rsplit(".", 1)[-1])
    with open(dst, "wb") as f:
        f.write(result)
    print(f"готово: {dst}")
