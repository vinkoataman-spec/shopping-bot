import json
import logging
import os
from pathlib import Path

# Railway: Volume дає RAILWAY_VOLUME_MOUNT_PATH — пишемо туди. Інакше /tmp (завжди доступний для запису).
_volume_path = os.getenv("RAILWAY_VOLUME_MOUNT_PATH")
if _volume_path:
    DATA_FILE = Path(_volume_path) / "data.json"
else:
    _on_railway = bool(os.getenv("RAILWAY_SERVICE_NAME") or os.getenv("RAILWAY_PROJECT_NAME"))
    _fallback = "/tmp/shopping_bot_data.json" if _on_railway else "data.json"
    DATA_FILE = Path(os.getenv("DATA_FILE", _fallback))
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


def _load_all() -> dict:
    """Повний вміст файлу. Міграція зі старого формату (один список) → families.default."""
    if not DATA_FILE.exists():
        return {"families": {}}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.exception("Помилка читання %s: %s", DATA_FILE, e)
        return {"families": {}}
    if "families" in data:
        return data
    # Старий формат: один спільний список → сім'я "default"
    families = {}
    if "shopping_list" in data:
        families["default"] = {
            "shopping_list": list(data.get("shopping_list", [])),
            "all_products": list(data.get("all_products", [])),
            "checked": list(data.get("checked", [])),
        }
    else:
        old_lists = data.get("shopping_lists", {})
        merged = []
        if isinstance(old_lists, dict):
            for items in old_lists.values():
                if isinstance(items, list):
                    merged.extend(items)
        families["default"] = {
            "shopping_list": merged,
            "all_products": list(data.get("all_products", [])),
            "checked": [],
        }
    return {"families": families}


def load_data(family_id: str):
    """Повертає (список покупок, множина товарів, множина позначених) для цієї сім'ї."""
    data = _load_all()
    if family_id not in data["families"]:
        return [], set(), set()
    c = data["families"][family_id]
    return (
        list(c.get("shopping_list", [])),
        set(c.get("all_products", [])),
        set(c.get("checked", [])),
    )


def save_data(family_id: str, shopping_list, all_products, checked=None):
    """Зберігає список для цієї сім'ї."""
    if checked is None:
        checked = set()
    data = _load_all()
    data["families"][family_id] = {
        "shopping_list": list(shopping_list),
        "all_products": list(all_products),
        "checked": list(checked),
    }
    path = Path(DATA_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        tmp.replace(path)
    except OSError as e:
        logger.exception("Помилка збереження даних: %s", e)
        raise
