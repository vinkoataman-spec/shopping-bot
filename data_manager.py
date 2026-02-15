import json
import logging
from pathlib import Path

DATA_FILE = Path("data.json")
logger = logging.getLogger(__name__)

# Максимальна довжина callback_data в Telegram — 64 байти
CALLBACK_DATA_MAX_BYTES = 64


def truncate_for_callback(text: str, prefix: str) -> str:
    """Обрізає текст так, щоб prefix + text у UTF-8 не перевищував 64 байти."""
    max_bytes = CALLBACK_DATA_MAX_BYTES - len(prefix.encode("utf-8"))
    b = text.encode("utf-8")
    if len(b) <= max_bytes:
        return text
    return b[:max_bytes].decode("utf-8", errors="ignore") or text[:1]


def load_data():
    if not DATA_FILE.exists():
        return {}, set()

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.exception("Помилка читання %s: %s", DATA_FILE, e)
        return {}, set()

    shopping_lists = {
        int(k): v
        for k, v in data.get("shopping_lists", {}).items()
    }
    all_products = set(data.get("all_products", []))
    return shopping_lists, all_products


def save_data(shopping_lists, all_products):
    # Ключі словника мають бути рядками для JSON
    data = {
        "shopping_lists": {str(uid): items for uid, items in shopping_lists.items()},
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
