"""
Список сімей: user_id → сім'я.
Редагуй families.json — додай Telegram ID учасників у масив своєї сім'ї.
Формат: {"family_1": [123456789, 987654321], "family_2": [111222333]}
Як дізнатися свій ID: напиши боту @userinfobot або подивись в URL профілю.
"""
import json
import logging
from pathlib import Path

FAMILIES_FILE = Path(__file__).parent / "families.json"
logger = logging.getLogger(__name__)

_cache: dict[str, list[int]] = {}
_cache_loaded = False


def _load_families() -> dict[str, list[int]]:
    global _cache_loaded
    if _cache_loaded:
        return _cache
    _cache_loaded = True
    if not FAMILIES_FILE.exists():
        return _cache
    try:
        with open(FAMILIES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Не вдалося прочитати %s: %s", FAMILIES_FILE, e)
        return _cache
    for key, ids in data.items():
        if isinstance(ids, list):
            _cache[key] = [int(x) for x in ids if isinstance(x, (int, float, str)) and str(x).isdigit()]
        else:
            _cache[key] = []
    return _cache


def get_family_id(user_id: int) -> str:
    """Повертає id сім'ї для цього user_id. Якщо не в жодній — повертає 'default' (спільний список)."""
    families = _load_families()
    for family_id, ids in families.items():
        if user_id in ids:
            return family_id
    return "default"
