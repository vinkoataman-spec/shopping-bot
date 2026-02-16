import json
import logging
import os
from pathlib import Path

# Railway: якщо додаси Volume до сервісу, Railway сам ставить RAILWAY_VOLUME_MOUNT_PATH —
# тоді зберігаємо data.json там (дані не пропадуть після редеплою).
# Інакше використовуємо DATA_FILE з env або data.json у поточній папці.
_volume_path = os.getenv("RAILWAY_VOLUME_MOUNT_PATH")
DATA_FILE = Path(_volume_path) / "data.json" if _volume_path else Path(os.getenv("DATA_FILE", "data.json"))
logger = logging.getLogger(__name__)

# Максимальна довжина callback_data / inline result id в Telegram — 64 байти
CALLBACK_DATA_MAX_BYTES = 64


def truncate_for_callback(text: str, prefix: str) -> str:
    """Обрізає текст так, щоб prefix + text у UTF-8 не перевищував 64 байти."""
    max_bytes = CALLBACK_DATA_MAX_BYTES - len(prefix.encode("utf-8"))
    b = text.encode("utf-8")
    if len(b) <= max_bytes:
        return text
    return b[:max_bytes].decode("utf-8", errors="ignore") or text[:1]


def load_data():
    """Повертає (спільний список покупок, множина всіх товарів для підказок)."""
    if not DATA_FILE.exists():
        return [], set()

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.exception("Помилка читання %s: %s", DATA_FILE, e)
        return [], set()

    # Новий формат: один список для всіх
    if "shopping_list" in data:
        shopping_list = list(data.get("shopping_list", []))
        all_products = set(data.get("all_products", []))
        return shopping_list, all_products

    # Міграція зі старого формату (списки по user_id) — об'єднуємо в один
    old_lists = data.get("shopping_lists", {})
    if isinstance(old_lists, dict):
        merged = []
        for items in old_lists.values():
            if isinstance(items, list):
                merged.extend(items)
        all_products = set(data.get("all_products", [])) | set(merged)
        return merged, all_products

    return [], set(data.get("all_products", []))


def save_data(shopping_list, all_products):
    """Зберігає спільний список і множину товарів."""
    data = {
        "shopping_list": list(shopping_list),
        "all_products": list(all_products),
    }
    path = Path(DATA_FILE)
    tmp = path.with_suffix(".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        tmp.replace(path)
    except OSError as e:
        logger.exception("Помилка збереження даних: %s", e)
        raise
