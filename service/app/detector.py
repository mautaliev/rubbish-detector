import base64
import io
from collections import Counter
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont
from ultralytics import YOLO

ROOT_DIR = Path(__file__).resolve().parents[2]
MODEL_1C_PATH = ROOT_DIR / "models" / "rubbish-detector-1c.pt"
MODEL_5C_PATH = ROOT_DIR / "models" / "rubbish-detector-5c.pt"

_model_1c: Optional[YOLO] = None
_model_5c: Optional[YOLO] = None


def _strip_data_url(value: str) -> str:
    """Убирает префикс data URL и возвращает чистую base64-строку.

    Args:
        value: Строка в формате base64 или data URL (например, 'data:image/jpeg;base64,...').

    Returns:
        str: Чистая base64-строка без префикса data URL.
    """
    if "," in value and value.strip().startswith("data:"):
        return value.split(",", 1)[1]
    return value


def decode_image(image_base64: str) -> Image.Image:
    """Декодирует base64-строку или data URL в RGB PIL-изображение.

    Args:
        image_base64: Изображение в формате base64 или data URL.

    Returns:
        Image.Image: Декодированное изображение в цветовом режиме RGB.
    """
    raw = base64.b64decode(_strip_data_url(image_base64))
    return Image.open(io.BytesIO(raw)).convert("RGB")


def encode_image(image: Image.Image) -> str:
    """Кодирует PIL-изображение в base64-строку в формате JPEG.

    Args:
        image: PIL-изображение для кодирования.

    Returns:
        str: Изображение в формате base64.
    """
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=92)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


def _load_model(detect_class: bool) -> YOLO:
    """Загружает и кэширует YOLO-модель.

    Args:
        detect_class: Если True — загружается 5-классовая модель, иначе 1-классовая.

    Returns:
        YOLO: Загруженная модель.

    Raises:
        FileNotFoundError: Если файл модели не найден.
    """
    global _model_1c, _model_5c

    model_path = MODEL_5C_PATH if detect_class else MODEL_1C_PATH
    if not model_path.exists():
        raise FileNotFoundError(f"Model file not found: {model_path}")

    if detect_class:
        if _model_5c is None:
            _model_5c = YOLO(str(model_path))
        return _model_5c

    if _model_1c is None:
        _model_1c = YOLO(str(model_path))
    return _model_1c


def _class_name(model: YOLO, class_id: int, detect_class: bool) -> str:
    """Возвращает название класса обнаруженного объекта.

    Args:
        model: Загруженная YOLO-модель со словарём классов.
        class_id: Числовой идентификатор класса из предсказания модели.
        detect_class: Если False — всегда возвращает 'rubbish' независимо от class_id.

    Returns:
        str: Название класса объекта.
    """
    if not detect_class:
        return "rubbish"
    names = getattr(model, "names", {}) or {}
    return str(names.get(class_id, f"class_{class_id}"))


def _draw_box(draw: ImageDraw.ImageDraw, box, label: str) -> None:
    """Рисует ограничивающий прямоугольник и подпись на изображении.

    Args:
        draw: Объект ImageDraw для рисования на изображении.
        box: Координаты прямоугольника в формате [x1, y1, x2, y2].
        label: Текст подписи (название класса и уверенность модели).
    """
    x1, y1, x2, y2 = [int(v) for v in box]
    box_h = y2 - y1
    width = max(1, round((x2 - x1 + box_h) / 400))
    font_size = max(12, min(22, int(box_h * 0.12)))

    draw.rectangle((x1, y1, x2, y2), outline="red", width=width)

    try:
        font = ImageFont.truetype("DejaVuSans.ttf", size=font_size)
    except Exception:
        font = ImageFont.load_default()

    text_box = draw.textbbox((x1, y1), label, font=font)
    text_w = text_box[2] - text_box[0]
    text_h = text_box[3] - text_box[1]
    text_y = max(0, y1 - text_h - 6)

    draw.rectangle((x1, text_y, x1 + text_w + 8, text_y + text_h + 6), fill="red")
    draw.text((x1 + 4, text_y + 3), label, fill="white", font=font)


def detect(image: Image.Image, detect_class: bool = False, conf: float = 0.25) -> dict:
    """Запускает детекцию мусора на изображении.

    Args:
        image: Входное PIL-изображение для анализа.
        detect_class: Если True — используется 5-классовая модель с разбивкой по типам мусора.
        conf: Порог уверенности модели от 0 до 1; объекты ниже порога отбрасываются.

    Returns:
        dict: Словарь с ключами:
            - image (Image.Image | None): Изображение с нанесёнными рамками или None если ничего не найдено.
            - found (dict | None): Словарь вида {название_класса: {"count": N}} или None.
            - total (int): Общее количество обнаруженных объектов.
    """
    model = _load_model(detect_class)
    results = model.predict(image, conf=conf, verbose=False)
    result = results[0]

    boxes = getattr(result, "boxes", None)
    if boxes is None or len(boxes) == 0:
        return {"image": None, "found": None, "total": 0}

    annotated = image.copy()
    draw = ImageDraw.Draw(annotated)
    counter = Counter()

    for item in boxes:
        class_id = int(item.cls[0].item()) if item.cls is not None else 0
        confidence = float(item.conf[0].item()) if item.conf is not None else 0.0
        name = _class_name(model, class_id, detect_class)
        counter[name] += 1

        label = f"{name} {confidence:.2f}" if detect_class else f"rubbish {confidence:.2f}"
        _draw_box(draw, item.xyxy[0].tolist(), label)

    found = {name: {"count": count} for name, count in counter.items()}
    return {"image": annotated, "found": found, "total": sum(counter.values())}
