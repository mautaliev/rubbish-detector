import base64
import io
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image, ImageDraw

from service.app.detector import (
    _class_name,
    _draw_box,
    _strip_data_url,
    decode_image,
    detect,
    encode_image,
)


# ---------------------------------------------------------------------------
# _strip_data_url
# ---------------------------------------------------------------------------

class TestStripDataUrl:
    """Тесты функции _strip_data_url, которая убирает data URL-префикс из base64-строки."""

    def test_strips_jpeg_prefix(self):
        """Убеждаемся, что JPEG data URL корректно обрезается до чистой base64-строки."""
        result = _strip_data_url("data:image/jpeg;base64,abc123")
        assert result == "abc123"

    def test_strips_png_prefix(self):
        """Убеждаемся, что PNG data URL корректно обрезается до чистой base64-строки."""
        result = _strip_data_url("data:image/png;base64,xyz==")
        assert result == "xyz=="

    def test_passes_through_plain_base64(self):
        """Строка без префикса data URL должна возвращаться без изменений."""
        b64 = "iVBORw0KGgo="
        assert _strip_data_url(b64) == b64

    def test_passes_through_empty_string(self):
        """Пустая строка должна возвращаться без изменений и не вызывать исключений."""
        assert _strip_data_url("") == ""

    def test_comma_but_no_data_prefix(self):
        """Строка с запятой, но без префикса 'data:', должна возвращаться как есть."""
        value = "something,else"
        assert _strip_data_url(value) == value


# ---------------------------------------------------------------------------
# decode_image
# ---------------------------------------------------------------------------

class TestDecodeImage:
    """Тесты функции decode_image, которая преобразует base64-строку или data URL в RGB PIL-изображение."""

    def test_decode_plain_base64(self, sample_base64):
        """Чистая base64-строка должна декодироваться в RGB PIL-изображение."""
        img = decode_image(sample_base64)
        assert isinstance(img, Image.Image)
        assert img.mode == "RGB"

    def test_decode_data_url(self, sample_data_url):
        """Data URL должен декодироваться в RGB PIL-изображение так же, как чистый base64."""
        img = decode_image(sample_data_url)
        assert isinstance(img, Image.Image)
        assert img.mode == "RGB"

    def test_decoded_size_matches_original(self, sample_image, sample_base64):
        """Размер декодированного изображения должен совпадать с размером исходного."""
        img = decode_image(sample_base64)
        assert img.size == sample_image.size

    def test_invalid_base64_raises(self):
        """Невалидная base64-строка должна приводить к исключению."""
        with pytest.raises(Exception):
            decode_image("not-valid-base64!!!")


# ---------------------------------------------------------------------------
# encode_image
# ---------------------------------------------------------------------------

class TestEncodeImage:
    """Тесты функции encode_image, которая кодирует PIL-изображение в JPEG base64-строку."""

    def test_returns_string(self, sample_image):
        """Результат encode_image должен быть строкой."""
        result = encode_image(sample_image)
        assert isinstance(result, str)

    def test_result_is_valid_base64(self, sample_image):
        """Возвращаемая строка должна успешно декодироваться из base64 и содержать данные."""
        result = encode_image(sample_image)
        decoded = base64.b64decode(result)
        assert len(decoded) > 0

    def test_result_is_valid_jpeg(self, sample_image):
        """Декодированные байты должны представлять валидный JPEG-файл."""
        result = encode_image(sample_image)
        raw = base64.b64decode(result)
        img = Image.open(io.BytesIO(raw))
        assert img.format == "JPEG"

    def test_roundtrip_preserves_size(self, sample_image):
        """После encode→decode размер изображения должен сохраниться."""
        encoded = encode_image(sample_image)
        raw = base64.b64decode(encoded)
        restored = Image.open(io.BytesIO(raw)).convert("RGB")
        assert restored.size == sample_image.size


# ---------------------------------------------------------------------------
# _class_name
# ---------------------------------------------------------------------------

class TestClassName:
    """Тесты функции _class_name, которая возвращает текстовое название класса обнаруженного объекта."""

    def _make_model(self, names: dict) -> MagicMock:
        """Создаёт мок YOLO-модели с заданным словарём имён классов."""
        model = MagicMock()
        model.names = names
        return model

    def test_returns_rubbish_when_detect_class_false(self):
        """При detect_class=False функция всегда возвращает 'rubbish', игнорируя class_id."""
        model = self._make_model({0: "plastic", 1: "glass"})
        assert _class_name(model, 0, detect_class=False) == "rubbish"
        assert _class_name(model, 1, detect_class=False) == "rubbish"

    def test_returns_class_name_when_detect_class_true(self):
        """При detect_class=True возвращается имя класса из словаря модели."""
        model = self._make_model({0: "plastic", 1: "glass"})
        assert _class_name(model, 0, detect_class=True) == "plastic"
        assert _class_name(model, 1, detect_class=True) == "glass"

    def test_fallback_when_class_id_missing(self):
        """Если class_id отсутствует в словаре, возвращается строка вида 'class_N'."""
        model = self._make_model({0: "plastic"})
        assert _class_name(model, 99, detect_class=True) == "class_99"

    def test_model_without_names_attribute(self):
        """Модель без атрибута names не должна вызывать исключение — возвращается 'class_N'."""
        model = MagicMock(spec=[])
        assert _class_name(model, 0, detect_class=True) == "class_0"


# ---------------------------------------------------------------------------
# _draw_box
# ---------------------------------------------------------------------------

class TestDrawBox:
    """Тесты функции _draw_box, которая рисует bounding box и подпись на PIL-изображении."""

    def test_draws_without_exception(self, sample_image):
        """Рисование рамки и подписи на корректном изображении не должно вызывать исключений."""
        draw = ImageDraw.Draw(sample_image)
        _draw_box(draw, [2, 2, 18, 18], "rubbish 0.95")

    def test_large_image_draws_without_exception(self):
        """Рисование рамки на большом изображении (640×480) не должно вызывать исключений."""
        img = Image.new("RGB", (640, 480), color=(0, 0, 0))
        draw = ImageDraw.Draw(img)
        _draw_box(draw, [10, 10, 200, 150], "plastic 0.80")

    def test_box_at_top_edge(self, sample_image):
        """Рамка с y1=0 не должна вызывать исключений при отрисовке текста выше верхнего края."""
        draw = ImageDraw.Draw(sample_image)
        _draw_box(draw, [0, 0, 10, 10], "rubbish 0.50")


# ---------------------------------------------------------------------------
# _load_model
# ---------------------------------------------------------------------------

class TestLoadModel:
    """Тесты функции _load_model: загрузка YOLO-модели, кэширование и выбор нужного файла весов."""

    def test_raises_file_not_found_when_model_missing(self, tmp_path, monkeypatch):
        """Если файл модели отсутствует на диске, должен подниматься FileNotFoundError."""
        import service.app.detector as detector_module
        monkeypatch.setattr(detector_module, "MODEL_1C_PATH", tmp_path / "missing.pt")
        monkeypatch.setattr(detector_module, "MODEL_5C_PATH", tmp_path / "missing5c.pt")
        monkeypatch.setattr(detector_module, "_model_1c", None)
        monkeypatch.setattr(detector_module, "_model_5c", None)

        with pytest.raises(FileNotFoundError, match="Model file not found"):
            detector_module._load_model(detect_class=False)

    def test_model_is_cached(self, tmp_path, monkeypatch):
        """Повторный вызов _load_model с теми же параметрами должен возвращать один объект без повторной инициализации YOLO."""
        import service.app.detector as detector_module

        model_path = tmp_path / "fake.pt"
        model_path.touch()

        monkeypatch.setattr(detector_module, "MODEL_1C_PATH", model_path)
        monkeypatch.setattr(detector_module, "_model_1c", None)

        fake_model = MagicMock()
        with patch("service.app.detector.YOLO", return_value=fake_model) as mock_yolo:
            m1 = detector_module._load_model(detect_class=False)
            m2 = detector_module._load_model(detect_class=False)

        assert m1 is m2
        mock_yolo.assert_called_once()

    def test_selects_5c_model_when_detect_class_true(self, tmp_path, monkeypatch):
        """При detect_class=True должен загружаться файл 5-классовой модели (MODEL_5C_PATH)."""
        import service.app.detector as detector_module

        model_path = tmp_path / "fake5c.pt"
        model_path.touch()

        monkeypatch.setattr(detector_module, "MODEL_5C_PATH", model_path)
        monkeypatch.setattr(detector_module, "_model_5c", None)

        fake_model = MagicMock()
        with patch("service.app.detector.YOLO", return_value=fake_model):
            result = detector_module._load_model(detect_class=True)

        assert result is fake_model


# ---------------------------------------------------------------------------
# detect
# ---------------------------------------------------------------------------

def _make_fake_box(x1=5, y1=5, x2=15, y2=15, class_id=0, confidence=0.9):
    """Создаёт мок одного детектированного объекта (bounding box) с заданными координатами и уверенностью."""
    box = MagicMock()
    import torch
    box.xyxy = [MagicMock(tolist=lambda: [x1, y1, x2, y2])]
    box.cls = MagicMock()
    box.cls.__getitem__ = lambda self, i: MagicMock(item=lambda: class_id)
    box.conf = MagicMock()
    box.conf.__getitem__ = lambda self, i: MagicMock(item=lambda: confidence)
    return box


class TestDetect:
    """Тесты функции detect: запуск инференса, аннотирование изображения и формирование результата."""

    def _patch_load_model(self, monkeypatch, boxes):
        """Подменяет _load_model моком модели, возвращающей заданный список bounding box'ов."""
        fake_model = MagicMock()
        fake_model.names = {0: "plastic"}

        fake_boxes = MagicMock()
        fake_boxes.__len__ = lambda self: len(boxes)
        fake_boxes.__iter__ = lambda self: iter(boxes)

        fake_result = MagicMock()
        fake_result.boxes = fake_boxes

        fake_model.predict.return_value = [fake_result]

        import service.app.detector as detector_module
        monkeypatch.setattr(detector_module, "_load_model", lambda detect_class: fake_model)
        return fake_model

    def test_returns_none_image_when_no_boxes(self, sample_image, monkeypatch):
        """Когда модель возвращает boxes=None, detect должен вернуть image=None, found=None, total=0."""
        import service.app.detector as detector_module

        fake_model = MagicMock()
        fake_result = MagicMock()
        fake_result.boxes = None
        fake_model.predict.return_value = [fake_result]
        monkeypatch.setattr(detector_module, "_load_model", lambda dc: fake_model)

        result = detect(sample_image)

        assert result["image"] is None
        assert result["found"] is None
        assert result["total"] == 0

    def test_returns_none_image_when_empty_boxes(self, sample_image, monkeypatch):
        """Когда список boxes пуст, detect должен вернуть image=None и total=0."""
        import service.app.detector as detector_module

        fake_model = MagicMock()
        fake_boxes = MagicMock()
        fake_boxes.__len__ = lambda self: 0
        fake_result = MagicMock()
        fake_result.boxes = fake_boxes
        fake_model.predict.return_value = [fake_result]
        monkeypatch.setattr(detector_module, "_load_model", lambda dc: fake_model)

        result = detect(sample_image)

        assert result["image"] is None
        assert result["total"] == 0

    def test_detect_returns_annotated_image(self, sample_image, monkeypatch):
        """При наличии одного bounding box detect должен вернуть аннотированное изображение и found с одним объектом."""
        box = _make_fake_box()
        self._patch_load_model(monkeypatch, [box])

        result = detect(sample_image, detect_class=False)

        assert isinstance(result["image"], Image.Image)
        assert result["total"] == 1
        assert "rubbish" in result["found"]
        assert result["found"]["rubbish"]["count"] == 1

    def test_detect_counts_multiple_boxes(self, sample_image, monkeypatch):
        """Три одинаковых bounding box'а должны суммироваться в total=3 и count=3 для класса."""
        boxes = [_make_fake_box(), _make_fake_box(), _make_fake_box()]
        self._patch_load_model(monkeypatch, boxes)

        result = detect(sample_image, detect_class=False)

        assert result["total"] == 3
        assert result["found"]["rubbish"]["count"] == 3

    def test_detect_with_detect_class_uses_model_names(self, sample_image, monkeypatch):
        """При detect_class=True каждый класс должен попасть в found под своим именем из model.names."""
        import service.app.detector as detector_module

        fake_model = MagicMock()
        fake_model.names = {0: "plastic", 1: "glass"}

        box0 = _make_fake_box(class_id=0)
        box1 = _make_fake_box(class_id=1)

        fake_boxes = MagicMock()
        fake_boxes.__len__ = lambda self: 2
        fake_boxes.__iter__ = lambda self: iter([box0, box1])

        fake_result = MagicMock()
        fake_result.boxes = fake_boxes
        fake_model.predict.return_value = [fake_result]

        monkeypatch.setattr(detector_module, "_load_model", lambda dc: fake_model)

        result = detect(sample_image, detect_class=True)

        assert result["total"] == 2
        assert "plastic" in result["found"]
        assert "glass" in result["found"]

    def test_detect_passes_conf_to_model(self, sample_image, monkeypatch):
        """Параметр conf должен передаваться в model.predict без изменений."""
        import service.app.detector as detector_module

        fake_model = MagicMock()
        fake_result = MagicMock()
        fake_result.boxes = None
        fake_model.predict.return_value = [fake_result]
        monkeypatch.setattr(detector_module, "_load_model", lambda dc: fake_model)

        detect(sample_image, conf=0.7)

        fake_model.predict.assert_called_once_with(sample_image, conf=0.7, verbose=False)
