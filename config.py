import os

from dotenv import load_dotenv

load_dotenv()

# Токен з змінної середовища (Railway, .env). Для локальної розробки задай BOT_TOKEN у .env
TOKEN = os.getenv("BOT_TOKEN", "")
