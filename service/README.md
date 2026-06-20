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

### С Docker (рекомендуется)

```bash
cp .env.example .env                          # вписать DB_PASSWORD
docker-compose up -d --build                  # поднять app + db
docker-compose exec app alembic upgrade head  # применить миграции
```

Веб-страница: `http://localhost:8000`  
Swagger: `http://localhost:8000/docs`

### Остановка Docker-контейнеров

```bash
docker-compose down          # остановить и удалить контейнеры
docker-compose down -v       # также удалить volumes (данные БД будут потеряны)
```

### Пересборка контейнеров после изменений в коде

Простой `docker-compose up -d` поднимает закэшированный образ — код не обновляется.

```bash
docker-compose down
docker-compose up -d --build          # пересобрать образ и запустить
```

Если изменения всё равно не применяются:

```bash
docker-compose build --no-cache       # полная пересборка без кэша
docker-compose up -d
```

> **Важно:** если вы запускаете сервис локально через `uvicorn` без Docker, пересборка контейнеров не имеет эффекта. Убедитесь, что нужные переменные окружения заданы в shell:
>
> ```bash
> echo $ENVIRONMENT
> echo $TESTLAB_ENABLED
> ```

### Без Docker (только сервис, без БД)

```bash
pip install -r requirements.txt
uvicorn service.app.main:app --reload --host 0.0.0.0 --port 8000
```

## База данных

Схема хранится в `service/db/`, миграции — в `service/db/alembic/`.

| Таблица | Описание |
|---|---|
| `company` | Управляющие компании (УК) |
| `cleaner` | Дворники, привязанные к УК |
| `report` | Отчёты детекции с результатами по каждому фото |

Добавить новую миграцию:

```bash
alembic revision -m "описание изменения"
# отредактировать созданный файл в service/db/alembic/versions/
alembic upgrade head
```

Откатить последнюю миграцию:

```bash
alembic downgrade -1
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
