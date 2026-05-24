import json
import os
import platform
from pathlib import Path

import torch
from ultralytics import YOLO

from download_dataset import download as download_dataset


def is_colab() -> bool:
    return "COLAB_GPU" in os.environ or Path("/content").exists()


def get_device():
    if torch.cuda.is_available():
        print(f"Используется CUDA GPU: {torch.cuda.get_device_name(0)}")
        return 0

    if platform.system() == "Darwin" and torch.backends.mps.is_available():
        print("Используется Apple MPS")
        return "mps"

    print("GPU не найден, используется CPU")
    return "cpu"


def load_config(config_path: str = "config.json") -> dict:
    with open(config_path, "r", encoding="utf-8") as file:
        return json.load(file)


def run_training(config_path: str = "config.json"):
    config = load_config(config_path)

    colab = is_colab()
    device = get_device()

    data_path = config["data_colab"] if colab else config["data_local"]
    project_path = config["project_colab"] if colab else config["project_local"]

    print("Среда:", "Google Colab" if colab else "Локальный ПК")
    print("Датасет:", data_path)
    print("Папка результатов:", project_path)

    model = YOLO(config["model"])

    results = model.train(
        data=data_path,
        epochs=config["epochs"],
        imgsz=config["imgsz"],
        batch=config["batch"],
        device=device,
        workers=config["workers"],
        optimizer=config["optimizer"],
        plots=config["plots"],
        project=project_path,
        name=config["name"]
    )

    return results


if __name__ == "__main__":
    download_dataset()
    run_training()