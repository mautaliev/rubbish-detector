from datetime import datetime

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .detector import decode_image, detect, encode_image
from .schemas import DetectRequest, DetectResponse

app = FastAPI(title="Rubbish Detector API", version="1.0.0")
app.mount("/static", StaticFiles(directory="service/app/static"), name="static")

LOG_PATH = "requests.log.txt"


def get_client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    return request.client.host


def write_log(ip: str, path: str, body: str) -> None:
    """Записывает строку запроса в лог-файл.

    Args:
        ip: IP-адрес отправителя запроса.
        path: Путь эндпоинта, на который пришёл запрос.
        body: Описание тела запроса (файлы заменены строкой с размером).
    """
    with open(LOG_PATH, "a", encoding="utf-8") as log_file:
        log_file.write(
            f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "
            f"ip={ip} POST {path} {body}\n"
        )


@app.get("/")
def index():
    """Возвращает главную HTML-страницу сервиса."""
    return FileResponse("service/app/static/index.html")


@app.get("/privacy")
async def privacy():
    """Возвращает страницу политики конфиденциальности."""
    return FileResponse("service/app/static/privacy.html")


@app.post("/api/detect", response_model=DetectResponse)
def detect_from_base64(payload: DetectRequest, request: Request):
    """Принимает изображение в формате base64 и возвращает результат детекции мусора.

    Args:
        payload: Тело запроса с полями image_base64, detect_class и conf.
        request: Объект HTTP-запроса (используется для получения IP отправителя).

    Returns:
        DetectResponse: Аннотированное изображение в base64, найденные объекты и их общее количество.
    """
    image_size = len(payload.image_base64.encode())
    write_log(
        ip=get_client_ip(request),
        path="/api/detect",
        body=f"image=[base64, {image_size} bytes] detect_class={payload.detect_class} conf={payload.conf}",
    )
    try:
        image = decode_image(payload.image_base64)
        result = detect(image, detect_class=payload.detect_class, conf=payload.conf)

        if result["image"] is None:
            return {"image_base64": None, "found": None, "total": 0}

        return {
            "image_base64": encode_image(result["image"]),
            "found": result["found"],
            "total": result["total"],
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/detect-file")
async def detect_from_file(
    request: Request,
    file: UploadFile = File(...),
    detect_class: bool = Form(False),
    conf: float = Form(0.25),
):
    """Принимает изображение как multipart/form-data файл и возвращает результат детекции мусора.

    Args:
        request: Объект HTTP-запроса (используется для получения IP отправителя).
        file: Загружаемый файл изображения.
        detect_class: Если True — используется 5-классовая модель с разбивкой по типам мусора.
        conf: Порог уверенности модели от 0 до 1.

    Returns:
        dict: Аннотированное изображение в base64, найденные объекты и их общее количество.
    """
    try:
        data = await file.read()
        write_log(
            ip=get_client_ip(request),
            path="/api/detect-file",
            body=f"file=[{file.filename}, {len(data)} bytes] detect_class={detect_class} conf={conf}",
        )
        image_base64 = encode_bytes_to_base64(data)
        image = decode_image(image_base64)
        result = detect(image, detect_class=detect_class, conf=conf)

        if result["image"] is None:
            return {"image_base64": None, "found": None, "total": 0}

        return {
            "image_base64": encode_image(result["image"]),
            "found": result["found"],
            "total": result["total"],
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def encode_bytes_to_base64(data: bytes) -> str:
    """Кодирует байты в base64-строку.

    Args:
        data: Бинарные данные для кодирования.

    Returns:
        str: Данные в формате base64.
    """
    import base64

    return base64.b64encode(data).decode("utf-8")
