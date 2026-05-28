from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .detector import decode_image, detect, encode_image
from .schemas import DetectRequest, DetectResponse

app = FastAPI(title="Rubbish Detector API", version="1.0.0")
app.mount("/static", StaticFiles(directory="service/app/static"), name="static")


@app.get("/")
def index():
    """Возвращает главную HTML-страницу сервиса."""
    return FileResponse("service/app/static/index.html")


@app.get("/privacy")
async def privacy():
    """Возвращает страницу политики конфиденциальности."""
    return FileResponse("service/app/static/privacy.html")


@app.post("/api/detect", response_model=DetectResponse)
def detect_from_base64(payload: DetectRequest):
    """Принимает изображение в формате base64 и возвращает результат детекции мусора.

    Args:
        payload: Тело запроса с полями image_base64, detect_class и conf.

    Returns:
        DetectResponse: Аннотированное изображение в base64, найденные объекты и их общее количество.
    """
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
    file: UploadFile = File(...),
    detect_class: bool = Form(False),
    conf: float = Form(0.25),
):
    """Принимает изображение как multipart/form-data файл и возвращает результат детекции мусора.

    Args:
        file: Загружаемый файл изображения.
        detect_class: Если True — используется 5-классовая модель с разбивкой по типам мусора.
        conf: Порог уверенности модели от 0 до 1.

    Returns:
        dict: Аннотированное изображение в base64, найденные объекты и их общее количество.
    """
    try:
        data = await file.read()
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
