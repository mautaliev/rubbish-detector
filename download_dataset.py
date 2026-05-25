import json

from roboflow import Roboflow


def download():
    rf = Roboflow(api_key=get_api_key())
    project = rf.workspace("mautaliev").project("lst-taco-tyumen")
    version = project.version(1)
    version.download("yolov8")


def get_api_key():
    with open('api_keys.json', 'r') as file:
        api_key = json.loads(file.read())['roboflow']
    return api_key