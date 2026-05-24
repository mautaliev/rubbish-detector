from ultralytics import YOLO

model = YOLO("yolov8m.pt")

results = model.train(
    data="dataset/data.yaml",
    epochs=100,
    imgsz=1024,
    batch=4,
    device="mps",
    workers=0,
    verbose=True,
    plots=True
)