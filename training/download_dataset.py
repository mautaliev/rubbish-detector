import json

from roboflow import Roboflow


def download():
    """Скачивает датасет с Roboflow в формате YOLOv8."""
    rf = Roboflow(api_key=get_api_key())
    project = rf.workspace("mautaliev").project("ltt-rubbishdataset-1c")
    version = project.version(1)
    version.download("yolov8")


def get_api_key():
    """Читает API-ключ Roboflow из файла api_keys.json.

    Returns:
        str: API-ключ Roboflow.
    """
    with open('api_keys.json', 'r') as file:
        api_key = json.loads(file.read())['roboflow']
    return api_key
