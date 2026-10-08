import json
import os
import tempfile
from pathlib import Path


# Загрузка данных

async def load_data(data_file):
    try:
        with open(data_file, 'r', encoding='utf-8') as file:
            return json.load(file)
    except FileNotFoundError:
        return []


# Сохранение данных

async def save_data(data_file, data):
    """Атомарно сохраняет JSON: файл либо старый целиком, либо новый целиком."""
    data_file = Path(data_file)
    fd, tmp_path = tempfile.mkstemp(dir=data_file.parent, prefix=f".{data_file.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=4)
            file.flush()
            os.fsync(file.fileno())
        os.replace(tmp_path, data_file)
    except BaseException:
        Path(tmp_path).unlink(missing_ok=True)
        raise