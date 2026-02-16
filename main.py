import asyncio
import logging

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQueryResultArticle,
    InputTextMessageContent,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from aiogram.fsm.storage.memory import MemoryStorage

from config import TOKEN
from data_manager import load_data, save_data, truncate_for_callback

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

if not TOKEN:
    logger.error("Встановіть BOT_TOKEN у змінній середовища або в .env (див. .env.example)")
    raise SystemExit(1)

# ---------- Bot ----------
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())
BOT_USERNAME = ""

# ---------- Data: один спільний список для всіх користувачів ----------
shopping_list, all_products = load_data()


# ---------- Keyboards ----------
main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➕ Додати товар")],
        [KeyboardButton(text="📋 Поточний список")],
        [KeyboardButton(text="✅ Список виконано")],
    ],
    resize_keyboard=True
)


def inline_insert_keyboard():
    """Натиснув — у полі вводу зʼявляється @бот і пробіл."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="📝 Вставити @бота в поле вводу",
                switch_inline_query_current_chat=" "
            )]
        ]
    )


# ---------- Helpers ----------
def product_in_list(product: str) -> bool:
    return product in shopping_list


# ---------- Handlers ----------
@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer(
        "👋 <b>Вітаю!</b> Я бот для спільного списку покупок (для всієї родини).\n\n"
        "📌 <b>Що я вмію:</b>\n\n"
        "➕ <b>Додати товар</b> — натисни кнопку, потім «Вставити @бота в поле вводу». У полі зʼявиться @бот і пробіл — друкуй назву товару, зʼявляться підказки.\n\n"
        "📋 <b>Поточний список</b> — показує спільний список покупок.\n\n"
        "✅ <b>Список виконано</b> — очищає список після покупок.\n\n"
        "Команда /help — коротка підказка.",
        parse_mode="HTML",
        reply_markup=main_keyboard
    )


@dp.message(Command("help"))
async def help_cmd(message: types.Message):
    await message.answer(
        "📖 <b>Команди та кнопки</b>\n\n"
        "➕ <b>Додати товар</b> — натисни, потім кнопку в повідомленні: у полі вводу зʼявиться @бот, друкуй назву. У BotFather має бути Inline (/setinline).\n"
        "📋 <b>Поточний список</b> — переглянути спільний список.\n"
        "✅ <b>Список виконано</b> — очистити список після покупок.",
        parse_mode="HTML"
    )


@dp.message(lambda m: m.text == "➕ Додати товар")
async def add_product_prompt(message: types.Message):
    await message.answer(
        "Натисни кнопку нижче — у полі вводу одразу зʼявиться @бот і пробіл. Друкуй назву товару — зʼявляться підказки, можна додати одним натисканням.",
        reply_markup=inline_insert_keyboard()
    )


# ---------- Inline Mode ----------
def _safe_id(s: str, max_len: int = 60) -> str:
    """Унікальний id для inline результату (обмеження 64 байти)."""
    b = s.encode("utf-8")[:max_len]
    return b.decode("utf-8", errors="ignore") or "x"


@dp.inline_query()
async def inline_search(inline_query: types.InlineQuery):
    q = (inline_query.query or "").strip().lower()
    results = []

    if q:
        matches = sorted(p for p in all_products if q in p)[:15]
        for i, p in enumerate(matches):
            results.append(
                InlineQueryResultArticle(
                    id=f"p:{i}",
                    title=p,
                    input_message_content=InputTextMessageContent(
                        message_text=f"✅ Додано до списку: {p}"
                    ),
                )
            )
        if not matches:
            results.append(
                InlineQueryResultArticle(
                    id=_safe_id(f"n:{q}"),
                    title=f"➕ Такого товару немає. Додати «{q}»?",
                    input_message_content=InputTextMessageContent(
                        message_text=f"✅ Додано новий товар: {q}"
                    ),
                )
            )
    else:
        for i, p in enumerate(sorted(all_products)[:10]):
            results.append(
                InlineQueryResultArticle(
                    id=f"p:{i}",
                    title=p,
                    input_message_content=InputTextMessageContent(
                        message_text=f"✅ Додано до списку: {p}"
                    ),
                )
            )

    await inline_query.answer(results, cache_time=10)


@dp.chosen_inline_result()
async def chosen_inline(chosen: types.ChosenInlineResult):
    rid = chosen.result_id
    query = (chosen.query or "").strip().lower()

    if rid.startswith("p:"):
        try:
            idx = int(rid[2:])
        except ValueError:
            return
        matches = sorted(p for p in all_products if not query or query in p)[:15]
        if idx < 0 or idx >= len(matches):
            return
        product = matches[idx]
    elif rid.startswith("n:"):
        product = query if query else rid[2:]
        if not product:
            return
        all_products.add(product)
    else:
        return

    if product_in_list(product):
        return
    shopping_list.append(product)
    save_data(shopping_list, all_products)


@dp.message(lambda m: m.text == "📋 Поточний список")
async def show_list(message: types.Message):
    if not shopping_list:
        await message.answer("🛒 Список порожній")
        return
    text = "📝 Спільний список покупок:\n" + "\n".join(f"• {i}" for i in shopping_list)
    await message.answer(text)


@dp.message(lambda m: m.text == "✅ Список виконано")
async def clear_list(message: types.Message):
    global shopping_list
    shopping_list.clear()
    save_data(shopping_list, all_products)
    await message.answer("🎉 Список очищено!")


# ---------- Start ----------
async def main():
    global BOT_USERNAME, shopping_list, all_products
    me = await bot.get_me()
    BOT_USERNAME = me.username or "bot"
    logger.info("Бот запущено: @%s", BOT_USERNAME)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
