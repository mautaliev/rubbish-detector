# Rubbish Detector Service

FastAPI-сервис для запуска обученных YOLO-моделей через веб-страницу и JSON API.

## Модели

В корне репозитория должны лежать файлы:

```text
rubbish-detector-1c.pt
rubbish-detector-5c.pt
```

- `rubbish-detector-1c.pt` используется, когда `detect_class=false`.
- `rubbish-detector-5c.pt` используется, когда `detect_class=true`.

## Запуск

Из корня репозитория:

```bash
pip install -r requirements.txt
uvicorn service.app.main:app --reload --host 0.0.0.0 --port 8000
```

Веб-страница будет доступна по адресу:

```text
http://localhost:8000/
```

Swagger-документация API:

```text
http://localhost:8000/docs
```

## JSON API

`POST /api/detect`

Пример запроса:

```json
{
  "image_base64": "...",
  "detect_class": true,
  "conf": 0.25
}
```

Пример ответа, если загрязнение найдено:

```json
{
  "image_base64": "...",
  "found": {
    "plastic": { "count": 2 },
    "paper": { "count": 1 }
  },
  "total": 3
}
```

Пример ответа, если загрязнение не найдено:

```json
{
  "image_base64": null,
  "found": null,
  "total": 0
}
```

## Disclaimer

This project is published for educational and research purposes only.

The model was trained using publicly available datasets.  
Please check dataset licenses before any commercial usage.
