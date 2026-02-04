import json
from pathlib import Path

DATA_FILE = Path("data.json")


def load_data():
    if not DATA_FILE.exists():
        return {}, set()

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    shopping_lists = {
        int(user_id): items
        for user_id, items in data.get("shopping_lists", {}).items()
    }

    all_products = set(data.get("all_products", []))

    return shopping_lists, all_products


def save_data(shopping_lists, all_products):
    data = {
        "shopping_lists": shopping_lists,
        "all_products": list(all_products)
    }

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)