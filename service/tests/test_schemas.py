import pytest
from pydantic import ValidationError

from service.app.schemas import DetectRequest, DetectResponse, FoundItem


class TestDetectRequest:
    """Тесты Pydantic-модели DetectRequest: значения по умолчанию, валидация поля conf и обязательные поля."""

    def test_defaults(self):
        """detect_class и conf должны принимать значения по умолчанию (False и 0.25) при создании с одним полем."""
        req = DetectRequest(image_base64="abc123")
        assert req.detect_class is False
        assert req.conf == 0.25

    def test_custom_values(self):
        """Явно переданные значения detect_class и conf должны сохраняться в модели."""
        req = DetectRequest(image_base64="abc", detect_class=True, conf=0.5)
        assert req.detect_class is True
        assert req.conf == 0.5

    def test_conf_lower_bound(self):
        """Значение conf=0.0 должно проходить валидацию как допустимая нижняя граница."""
        req = DetectRequest(image_base64="abc", conf=0.0)
        assert req.conf == 0.0

    def test_conf_upper_bound(self):
        """Значение conf=1.0 должно проходить валидацию как допустимая верхняя граница."""
        req = DetectRequest(image_base64="abc", conf=1.0)
        assert req.conf == 1.0

    def test_conf_below_zero_raises(self):
        """Значение conf ниже 0.0 должно вызывать ValidationError."""
        with pytest.raises(ValidationError):
            DetectRequest(image_base64="abc", conf=-0.1)

    def test_conf_above_one_raises(self):
        """Значение conf выше 1.0 должно вызывать ValidationError."""
        with pytest.raises(ValidationError):
            DetectRequest(image_base64="abc", conf=1.1)

    def test_image_base64_required(self):
        """Создание DetectRequest без поля image_base64 должно вызывать ValidationError."""
        with pytest.raises(ValidationError):
            DetectRequest()


class TestFoundItem:
    """Тесты Pydantic-модели FoundItem: хранение количества найденных объектов одного класса."""

    def test_count_field(self):
        """Поле count должно корректно сохраняться и возвращаться."""
        item = FoundItem(count=5)
        assert item.count == 5


class TestDetectResponse:
    """Тесты Pydantic-модели DetectResponse: корректная структура ответа как при наличии детекций, так и без них."""

    def test_full_response(self):
        """Все поля DetectResponse должны корректно инициализироваться при наличии детекций."""
        resp = DetectResponse(
            image_base64="abc",
            found={"rubbish": FoundItem(count=2)},
            total=2,
        )
        assert resp.image_base64 == "abc"
        assert resp.total == 2
        assert resp.found["rubbish"].count == 2

    def test_empty_response(self):
        """DetectResponse должен допускать image_base64=None и found=None при отсутствии детекций."""
        resp = DetectResponse(image_base64=None, found=None, total=0)
        assert resp.image_base64 is None
        assert resp.found is None
        assert resp.total == 0
