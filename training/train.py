import json
import os
import platform

import torch
from ultralytics import YOLO

from download_dataset import download as download_dataset


def is_colab() -> bool:
    """Проверяет, запущен ли скрипт в среде Google Colab.

    Returns:
        bool: True если среда Google Colab, иначе False.
    """
    return "COLAB_GPU" in os.environ or os.path.exists("/content")


def get_device():
    """Определяет доступное устройство для обучения модели.

    Returns:
        int | str: 0 для CUDA GPU, 'mps' для Apple Silicon, 'cpu' если GPU недоступен.
    """
    if torch.cuda.is_available():
        print(f"Используется CUDA GPU: {torch.cuda.get_device_name(0)}")
        return 0

    if platform.system() == "Darwin" and torch.backends.mps.is_available():
        print("Используется Apple MPS")
        return "mps"

    print("GPU не найден, используется CPU")
    return "cpu"


def load_config(config_path: str = "config.json") -> dict:
    """Загружает конфигурацию обучения из JSON-файла.

    Args:
        config_path: Путь к JSON-файлу с конфигурацией.

    Returns:
        dict: Словарь с параметрами обучения.
    """
    with open(config_path, "r", encoding="utf-8") as file:
        return json.load(file)


def run_training(config_path: str = "config.json"):
    """Запускает обучение YOLO-модели согласно параметрам из конфигурационного файла.

    Args:
        config_path: Путь к JSON-файлу с конфигурацией обучения.

    Returns:
        ultralytics.engine.results.Results: Результаты обучения модели.
    """
    config = load_config(config_path)

    colab = is_colab()
    device = get_device()

    data_path = config["data"]
    project_path = config["project_colab"] if colab else config["project_local"]

    print("Среда:", "Google Colab" if colab else "Локальный ПК")
    print("Датасет:", data_path)
    print("Папка результатов:", project_path)

    model = YOLO(config["model"])
    results = model.train(
        data=data_path,
        project=project_path,
        device=device,
        epochs=config["epochs"],
        patience=config["patience"],
        imgsz=config["imgsz"],
        batch=config["batch"],
        workers=config["workers"],
        plots=config["plots"],
        name=config["name"],
    )
    return results


if __name__ == "__main__":
    if not os.path.exists(load_config()['data']):
        download_dataset()
    run_training()
