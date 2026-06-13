import base64
import io
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from service.app.main import app, encode_bytes_to_base64, get_client_ip, write_log


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_png_bytes(width: int = 20, height: int = 20) -> bytes:
    """Создаёт и возвращает байты PNG-изображения заданного размера для использования в тестах."""
    img = Image.new("RGB", (width, height), color=(80, 120, 160))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _png_base64(width: int = 20, height: int = 20) -> str:
    """Возвращает PNG-изображение, закодированное в строку base64, для передачи в JSON-тело запроса."""
    return base64.b64encode(_make_png_bytes(width, height)).decode()


def _make_detect_result(found: bool = True):
    """Создаёт словарь, имитирующий возвращаемое значение функции detect.

    Args:
        found: Если True — возвращает результат с одним найденным объектом,
               иначе — пустой результат без детекций.
    """
    if not found:
        return {"image": None, "found": None, "total": 0}
    img = Image.new("RGB", (20, 20))
    return {"image": img, "found": {"rubbish": {"count": 1}}, "total": 1}


@pytest.fixture()
def client():
    """Фикстура: возвращает TestClient для FastAPI-приложения с поднятым lifespan."""
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# get_client_ip
# ---------------------------------------------------------------------------

class TestGetClientIp:
    """Тесты функции get_client_ip: извлечение реального IP из заголовков прокси или напрямую из соединения."""

    def _make_request(self, headers: dict, host: str = "127.0.0.1"):
        """Создаёт мок HTTP-запроса с заданными заголовками и IP-адресом клиента."""
        request = MagicMock()
        request.headers = headers
        request.client = MagicMock()
        request.client.host = host
        return request

    def test_uses_x_forwarded_for(self):
        """Если присутствует заголовок X-Forwarded-For, должен извлекаться первый IP из цепочки."""
        req = self._make_request({"X-Forwarded-For": "1.2.3.4, 5.6.7.8"})
        assert get_client_ip(req) == "1.2.3.4"

    def test_uses_x_real_ip_when_no_forwarded_for(self):
        """Если X-Forwarded-For отсутствует, должен использоваться заголовок X-Real-IP."""
        req = self._make_request({"X-Real-IP": "9.10.11.12"})
        assert get_client_ip(req) == "9.10.11.12"

    def test_falls_back_to_client_host(self):
        """Если оба заголовка отсутствуют, должен возвращаться request.client.host."""
        req = self._make_request({}, host="192.168.1.1")
        assert get_client_ip(req) == "192.168.1.1"

    def test_x_forwarded_for_takes_priority_over_x_real_ip(self):
        """X-Forwarded-For должен иметь приоритет над X-Real-IP при наличии обоих заголовков."""
        req = self._make_request(
            {"X-Forwarded-For": "1.1.1.1", "X-Real-IP": "2.2.2.2"}
        )
        assert get_client_ip(req) == "1.1.1.1"

    def test_strips_whitespace_from_forwarded_for(self):
        """Пробелы вокруг первого IP в X-Forwarded-For должны обрезаться."""
        req = self._make_request({"X-Forwarded-For": "  3.3.3.3  , 4.4.4.4"})
        assert get_client_ip(req) == "3.3.3.3"


# ---------------------------------------------------------------------------
# write_log
# ---------------------------------------------------------------------------

class TestWriteLog:
    """Тесты функции write_log: создание лог-файла, корректность содержимого и режим дозаписи."""

    def test_creates_log_file(self, tmp_path, monkeypatch):
        """write_log должен создавать лог-файл, если он ещё не существует."""
        log_path = tmp_path / "test.log"
        monkeypatch.setattr("service.app.main.LOG_PATH", str(log_path))
        write_log("1.2.3.4", "/api/detect", "body")
        assert log_path.exists()

    def test_log_contains_ip(self, tmp_path, monkeypatch):
        """IP-адрес, переданный в write_log, должен присутствовать в записи лог-файла."""
        log_path = tmp_path / "test.log"
        monkeypatch.setattr("service.app.main.LOG_PATH", str(log_path))
        write_log("9.8.7.6", "/api/detect", "some body")
        content = log_path.read_text()
        assert "9.8.7.6" in content

    def test_log_contains_path(self, tmp_path, monkeypatch):
        """Путь эндпоинта, переданный в write_log, должен присутствовать в записи лог-файла."""
        log_path = tmp_path / "test.log"
        monkeypatch.setattr("service.app.main.LOG_PATH", str(log_path))
        write_log("0.0.0.0", "/api/detect-file", "body")
        assert "/api/detect-file" in log_path.read_text()

    def test_log_appends_multiple_entries(self, tmp_path, monkeypatch):
        """Каждый вызов write_log должен добавлять новую строку, не перезаписывая предыдущие."""
        log_path = tmp_path / "test.log"
        monkeypatch.setattr("service.app.main.LOG_PATH", str(log_path))
        write_log("1.1.1.1", "/api/detect", "first")
        write_log("2.2.2.2", "/api/detect", "second")
        lines = log_path.read_text().strip().splitlines()
        assert len(lines) == 2


# ---------------------------------------------------------------------------
# encode_bytes_to_base64
# ---------------------------------------------------------------------------

class TestEncodeBytesToBase64:
    """Тесты функции encode_bytes_to_base64: корректность кодирования и обработка граничных случаев."""

    def test_returns_string(self):
        """encode_bytes_to_base64 должен возвращать строку."""
        assert isinstance(encode_bytes_to_base64(b"hello"), str)

    def test_correct_encoding(self):
        """Результат должен совпадать со стандартным base64-кодированием тех же байт."""
        data = b"test data"
        assert encode_bytes_to_base64(data) == base64.b64encode(data).decode()

    def test_empty_bytes(self):
        """Кодирование пустых байт должно возвращать пустую строку."""
        assert encode_bytes_to_base64(b"") == ""


# ---------------------------------------------------------------------------
# GET /
# ---------------------------------------------------------------------------

class TestIndexEndpoint:
    """Тесты эндпоинта GET /: отдача главной HTML-страницы сервиса."""

    def test_returns_200(self, client):
        """GET / должен возвращать статус 200."""
        resp = client.get("/")
        assert resp.status_code == 200

    def test_content_type_html(self, client):
        """GET / должен возвращать HTML-контент (Content-Type: text/html)."""
        resp = client.get("/")
        assert "text/html" in resp.headers["content-type"]


# ---------------------------------------------------------------------------
# GET /privacy
# ---------------------------------------------------------------------------

class TestPrivacyEndpoint:
    """Тесты эндпоинта GET /privacy: отдача страницы политики конфиденциальности."""

    def test_returns_200(self, client):
        """GET /privacy должен возвращать статус 200."""
        resp = client.get("/privacy")
        assert resp.status_code == 200

    def test_content_type_html(self, client):
        """GET /privacy должен возвращать HTML-контент (Content-Type: text/html)."""
        resp = client.get("/privacy")
        assert "text/html" in resp.headers["content-type"]


# ---------------------------------------------------------------------------
# POST /api/detect
# ---------------------------------------------------------------------------

class TestDetectBase64Endpoint:
    """Тесты эндпоинта POST /api/detect: приём изображения в base64 и возврат результата детекции."""

    def test_success_with_detections(self, client, tmp_path, monkeypatch):
        """POST /api/detect с корректным изображением должен вернуть 200 с аннотированным изображением и найденными объектами."""
        monkeypatch.setattr("service.app.main.LOG_PATH", str(tmp_path / "log.txt"))
        img = Image.new("RGB", (20, 20))
        fake_result = {"image": img, "found": {"rubbish": {"count": 1}}, "total": 1}

        with patch("service.app.main.detect", return_value=fake_result), \
             patch("service.app.main.decode_image", return_value=img):
            resp = client.post(
                "/api/detect",
                json={"image_base64": _png_base64(), "detect_class": False, "conf": 0.25},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["image_base64"] is not None
        assert body["found"]["rubbish"]["count"] == 1

    def test_no_detections_returns_zero_total(self, client, tmp_path, monkeypatch):
        """Когда модель ничего не находит, ответ должен содержать total=0, image_base64=None, found=None."""
        monkeypatch.setattr("service.app.main.LOG_PATH", str(tmp_path / "log.txt"))
        img = Image.new("RGB", (20, 20))
        fake_result = {"image": None, "found": None, "total": 0}

        with patch("service.app.main.detect", return_value=fake_result), \
             patch("service.app.main.decode_image", return_value=img):
            resp = client.post(
                "/api/detect",
                json={"image_base64": _png_base64(), "detect_class": False, "conf": 0.25},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 0
        assert body["image_base64"] is None
        assert body["found"] is None

    def test_invalid_image_returns_400(self, client, tmp_path, monkeypatch):
        """Если decode_image поднимает исключение, эндпоинт должен вернуть HTTP 400."""
        monkeypatch.setattr("service.app.main.LOG_PATH", str(tmp_path / "log.txt"))

        with patch("service.app.main.decode_image", side_effect=ValueError("bad image")):
            resp = client.post(
                "/api/detect",
                json={"image_base64": "not-valid", "detect_class": False, "conf": 0.25},
            )

        assert resp.status_code == 400

    def test_missing_image_base64_returns_422(self, client):
        """Запрос без обязательного поля image_base64 должен возвращать HTTP 422."""
        resp = client.post("/api/detect", json={"detect_class": False})
        assert resp.status_code == 422

    def test_conf_out_of_range_returns_422(self, client):
        """Значение conf за пределами [0, 1] должно отклоняться валидатором Pydantic с HTTP 422."""
        resp = client.post(
            "/api/detect",
            json={"image_base64": "abc", "conf": 1.5},
        )
        assert resp.status_code == 422

    def test_passes_detect_class_to_detect(self, client, tmp_path, monkeypatch):
        """Флаг detect_class из тела запроса должен передаваться в функцию detect без изменений."""
        monkeypatch.setattr("service.app.main.LOG_PATH", str(tmp_path / "log.txt"))
        img = Image.new("RGB", (20, 20))
        fake_result = {"image": None, "found": None, "total": 0}

        with patch("service.app.main.detect", return_value=fake_result) as mock_detect, \
             patch("service.app.main.decode_image", return_value=img):
            client.post(
                "/api/detect",
                json={"image_base64": _png_base64(), "detect_class": True, "conf": 0.5},
            )

        mock_detect.assert_called_once_with(img, detect_class=True, conf=0.5)


# ---------------------------------------------------------------------------
# POST /api/detect-file
# ---------------------------------------------------------------------------

class TestDetectFileEndpoint:
    """Тесты эндпоинта POST /api/detect-file: приём изображения как multipart-файла и возврат результата детекции."""

    def test_success_with_detections(self, client, tmp_path, monkeypatch):
        """POST /api/detect-file с PNG-файлом должен вернуть 200 с аннотированным изображением."""
        monkeypatch.setattr("service.app.main.LOG_PATH", str(tmp_path / "log.txt"))
        img = Image.new("RGB", (20, 20))
        fake_result = {"image": img, "found": {"rubbish": {"count": 2}}, "total": 2}
        png_bytes = _make_png_bytes()

        with patch("service.app.main.detect", return_value=fake_result), \
             patch("service.app.main.decode_image", return_value=img):
            resp = client.post(
                "/api/detect-file",
                files={"file": ("test.png", png_bytes, "image/png")},
                data={"detect_class": "false", "conf": "0.25"},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        assert body["image_base64"] is not None

    def test_no_detections_returns_zero_total(self, client, tmp_path, monkeypatch):
        """Когда модель ничего не находит в загруженном файле, ответ должен содержать total=0 и image_base64=None."""
        monkeypatch.setattr("service.app.main.LOG_PATH", str(tmp_path / "log.txt"))
        img = Image.new("RGB", (20, 20))
        fake_result = {"image": None, "found": None, "total": 0}
        png_bytes = _make_png_bytes()

        with patch("service.app.main.detect", return_value=fake_result), \
             patch("service.app.main.decode_image", return_value=img):
            resp = client.post(
                "/api/detect-file",
                files={"file": ("test.png", png_bytes, "image/png")},
                data={"detect_class": "false", "conf": "0.25"},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 0
        assert body["image_base64"] is None

    def test_missing_file_returns_422(self, client):
        """Запрос без обязательного поля file должен возвращать HTTP 422."""
        resp = client.post("/api/detect-file", data={"conf": "0.25"})
        assert resp.status_code == 422

    def test_invalid_image_returns_400(self, client, tmp_path, monkeypatch):
        """Если decode_image поднимает исключение при обработке файла, эндпоинт должен вернуть HTTP 400."""
        monkeypatch.setattr("service.app.main.LOG_PATH", str(tmp_path / "log.txt"))

        with patch("service.app.main.decode_image", side_effect=ValueError("bad")):
            resp = client.post(
                "/api/detect-file",
                files={"file": ("test.png", b"not-an-image", "image/png")},
                data={"detect_class": "false", "conf": "0.25"},
            )

        assert resp.status_code == 400

    def test_passes_conf_and_detect_class_to_detect(self, client, tmp_path, monkeypatch):
        """Параметры detect_class и conf из form-data должны передаваться в функцию detect без изменений."""
        monkeypatch.setattr("service.app.main.LOG_PATH", str(tmp_path / "log.txt"))
        img = Image.new("RGB", (20, 20))
        fake_result = {"image": None, "found": None, "total": 0}
        png_bytes = _make_png_bytes()

        with patch("service.app.main.detect", return_value=fake_result) as mock_detect, \
             patch("service.app.main.decode_image", return_value=img):
            client.post(
                "/api/detect-file",
                files={"file": ("test.png", png_bytes, "image/png")},
                data={"detect_class": "true", "conf": "0.6"},
            )

        mock_detect.assert_called_once_with(img, detect_class=True, conf=pytest.approx(0.6))
