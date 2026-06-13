import os
from pathlib import Path

# Гарантируем, что рабочая директория всегда совпадает с корнем проекта,
# независимо от того, откуда запускается pytest (PyCharm, терминал, CI).
# Это необходимо, потому что main.py монтирует StaticFiles с относительным путём
# "service/app/static" на уровне импорта модуля.
os.chdir(Path(__file__).parent)
