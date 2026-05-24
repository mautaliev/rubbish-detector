from roboflow import Roboflow
with open('roboflow_api_key.txt', 'r') as file:
    api_key = file.read()
rf = Roboflow(api_key=api_key)
project = rf.workspace("mautaliev").project("lst-taco-tyumen")
version = project.version(1)
dataset = version.download("yolov8")