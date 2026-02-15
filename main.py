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
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
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

# ---------- FSM ----------
class AddProduct(StatesGroup):
    waiting_for_product = State()


class SearchingProducts(StatesGroup):
    waiting_query = State()


# ---------- Bot ----------
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())
BOT_USERNAME = ""  # встановлюється при старті (get_me)


# ---------- Data ----------
shopping_lists, all_products = load_data()


# ---------- Keyboards ----------
main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➕ Додати товар")],
        [KeyboardButton(text="📋 Поточний список")],
        [KeyboardButton(text="✅ Список виконано")],
        [KeyboardButton(text="🔍 Пошук товарів")],
    ],
    resize_keyboard=True
)


def done_inline_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Готово", callback_data="done")]
        ]
    )


async def clear_previous_done_keyboard(state: FSMContext, bot: Bot):
    """Прибирає кнопку «Готово» з попереднього повідомлення бота."""
    data = await state.get_data()
    chat_id = data.get("last_done_chat_id")
    message_id = data.get("last_done_message_id")
    if not chat_id or not message_id:
        return
    try:
        await bot.edit_message_reply_markup(
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[])
        )
    except Exception:
        pass


def search_results_keyboard(matches: list):
    """Інлайн-клавіатура: кнопки «Додати» для кожного товару + Готово."""
    prefix = "add_from_search:"
    rows = [
        [InlineKeyboardButton(
            text=f"➕ {p}",
            callback_data=prefix + truncate_for_callback(p, prefix)
        )]
        for p in matches
    ]
    rows.append([InlineKeyboardButton(text="✅ Готово", callback_data="done")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ---------- Helpers ----------
def product_in_current_list(user_id: int, product: str) -> bool:
    return product in shopping_lists.get(user_id, [])


# ---------- Handlers ----------
@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer(
        "👋 <b>Вітаю!</b> Я бот для списку покупок.\n\n"
        "📌 <b>Що я вмію:</b>\n\n"
        "➕ <b>Додати товар</b> — натисни кнопку і надсилай назви товарів (можна кілька підряд). "
        "Коли закінчиш, натисни «Готово».\n\n"
        "📋 <b>Поточний список</b> — показує всі товари, які ти додав(ла) і ще не купив(ла).\n\n"
        "✅ <b>Список виконано</b> — очищає список після того, як ти все купив(ла).\n\n"
        "🔍 <b>Пошук товарів</b> — кнопка відкриє режим пошуку (треба вводити і відправляти повідомлення).\n\n"
        "💬 <b>Підказки БЕЗ відправки</b> — так працює тільки один спосіб: у <b>полі вводу повідомлення</b> напиши <b>@ім'я_бота</b> і одразу літери (наприклад: <code>@бот мол</code>). Зʼявиться випадаючий список — обирай товар, не натискаючи «Відправити». Якщо такого товару немає — зʼявиться «Додати?».\n\n"
        "Команда /help — коротка підказка.",
        parse_mode="HTML",
        reply_markup=main_keyboard
    )


@dp.message(Command("help"))
async def help_cmd(message: types.Message):
    await message.answer(
        "📖 <b>Команди та кнопки</b>\n\n"
        "➕ <b>Додати товар</b> — ввести назви товарів (можна кілька підряд).\n"
        "📋 <b>Поточний список</b> — переглянути список покупок.\n"
        "✅ <b>Список виконано</b> — очистити список після покупок.\n"
        "🔍 <b>Пошук товарів</b> — вводиш слово, відправляєш — отримуєш список; додати можна одним натисканням.\n"
        "💬 <b>Підказки без відправки</b> — у полі вводу напиши @ім'я_бота і літери (наприклад @бот мол) — зʼявиться випадаючий список, можна вибрати товар не натискаючи «Відправити». У BotFather має бути увімкнено Inline (/setinline).",
        parse_mode="HTML"
    )


@dp.message(lambda m: m.text == "➕ Додати товар")
async def start_add(message: types.Message, state: FSMContext):
    await state.set_state(AddProduct.waiting_for_product)
    sent = await message.answer(
        "✍️ Напиши назву товару. Можеш надсилати кілька повідомлень підряд.\n\n"
        "Коли додаси всі товари — натисни кнопку <b>«Готово»</b> внизу.",
        parse_mode="HTML",
        reply_markup=done_inline_keyboard()
    )
    await state.update_data(
        last_done_chat_id=sent.chat.id,
        last_done_message_id=sent.message_id,
    )


MENU_BUTTONS = ("➕ Додати товар", "📋 Поточний список", "✅ Список виконано", "🔍 Пошук товарів")


@dp.message(AddProduct.waiting_for_product, lambda m: m.text and m.text in MENU_BUTTONS)
async def menu_pressed_while_adding(message: types.Message, state: FSMContext):
    sent = await message.answer(
        "👀 Схоже, ти забув вийти з режиму додавання.\n\n"
        "Або натисни кнопку <b>«Готово»</b> внизу, або продовжуй надсилати назви товарів.",
        parse_mode="HTML",
        reply_markup=done_inline_keyboard()
    )
    await state.update_data(
        last_done_chat_id=sent.chat.id,
        last_done_message_id=sent.message_id,
    )


@dp.message(AddProduct.waiting_for_product)
async def add_product(message: types.Message, state: FSMContext):
    product = message.text.strip().lower()
    user_id = message.from_user.id

    if not product:
        return

    if product_in_current_list(user_id, product):
        await message.answer("ℹ️ Цей товар вже є у поточному списку.")
        return

    shopping_lists.setdefault(user_id, []).append(product)
    all_products.add(product)
    save_data(shopping_lists, all_products)

    await clear_previous_done_keyboard(state, bot)
    sent = await message.answer(
        f"✅ «{product}» додано.\n"
        "Можеш продовжувати. Коли закінчиш — натисни «Готово» внизу.",
        reply_markup=done_inline_keyboard()
    )
    await state.update_data(
        last_done_chat_id=sent.chat.id,
        last_done_message_id=sent.message_id,
    )


@dp.callback_query(lambda c: c.data == "done")
async def done(callback: types.CallbackQuery, state: FSMContext):
    current = await state.get_state()
    await state.clear()
    if current and "SearchingProducts" in current:
        await callback.message.edit_text("👌 Пошук завершено")
    else:
        await callback.message.edit_text("👌 Режим додавання завершено")
    await callback.answer()


# ---------- Inline Mode (пиши @бота + літери — підказки без відправки) ----------
def _inline_id(prefix: str, text: str) -> str:
    return prefix + truncate_for_callback(text, prefix)


@dp.inline_query()
async def inline_search(inline_query: types.InlineQuery):
    q = (inline_query.query or "").strip().lower()
    results = []

    if q:
        matches = sorted(p for p in all_products if q in p)[:15]
        for p in matches:
            results.append(
                InlineQueryResultArticle(
                    id=_inline_id("p:", p),
                    title=p,
                    input_message_content=InputTextMessageContent(
                        message_text=f"✅ Додано до списку: {p}"
                    ),
                )
            )
        if not matches:
            # Такого товару немає — пропонуємо додати
            results.append(
                InlineQueryResultArticle(
                    id=_inline_id("n:", q),
                    title=f"➕ Такого товару немає. Додати «{q}»?",
                    input_message_content=InputTextMessageContent(
                        message_text=f"✅ Додано новий товар: {q}"
                    ),
                )
            )
    else:
        # Порожній запит — показати кілька останніх/популярних або підказку
        for p in sorted(all_products)[:10]:
            results.append(
                InlineQueryResultArticle(
                    id=_inline_id("p:", p),
                    title=p,
                    input_message_content=InputTextMessageContent(
                        message_text=f"✅ Додано до списку: {p}"
                    ),
                )
            )

    await inline_query.answer(results, cache_time=10)


@dp.chosen_inline_result()
async def chosen_inline(chosen: types.ChosenInlineResult):
    user_id = chosen.from_user.id
    rid = chosen.result_id

    if rid.startswith("p:"):
        product = rid[2:]
    elif rid.startswith("n:"):
        product = rid[2:]
        all_products.add(product)
    else:
        return

    if product_in_current_list(user_id, product):
        return
    shopping_lists.setdefault(user_id, []).append(product)
    save_data(shopping_lists, all_products)


# ---------- Пошук товарів ----------
@dp.message(lambda m: m.text == "🔍 Пошук товарів")
async def start_search(message: types.Message, state: FSMContext):
    await state.set_state(SearchingProducts.waiting_query)
    if not all_products:
        await message.answer(
            "🔍 Ще немає збережених товарів.\n"
            "Спочатку додай товари через кнопку «➕ Додати товар» — тоді зʼявиться пошук.",
            reply_markup=main_keyboard
        )
        await state.clear()
        return
    hint = f" Для підказок <b>без відправки</b> напиши у полі вводу <b>@{BOT_USERNAME}</b> і літери (наприклад: @{BOT_USERNAME} мол)." if BOT_USERNAME else ""
    await message.answer(
        "🔍 Тут ти вводиш слово і <b>відправляєш</b> повідомлення — тоді я показую варіанти. "
        "Так працює Telegram: я бачу лише вже відправлений текст.\n\n"
        "Можеш додати товар з списку одним натисканням. Коли закінчиш — натисни «Готово»."
        + hint,
        parse_mode="HTML",
        reply_markup=done_inline_keyboard()
    )


@dp.message(SearchingProducts.waiting_query, lambda m: m.text and m.text.strip() in MENU_BUTTONS)
async def menu_pressed_while_searching(message: types.Message, state: FSMContext):
    await message.answer(
        "👀 Ти зараз у режимі пошуку.\n\n"
        "Натисни кнопку <b>«Готово»</b> внизу, щоб вийти з пошуку.",
        parse_mode="HTML",
        reply_markup=done_inline_keyboard()
    )


@dp.message(SearchingProducts.waiting_query)
async def search_products(message: types.Message, state: FSMContext):
    query = message.text.strip().lower()
    if not query:
        return
    # Підходящі товари: ті, у назві яких є введений текст
    matches = sorted(p for p in all_products if query in p)[:15]
    if not matches:
        await message.answer(
            f"По запиту «{query}» нічого не знайдено. Спробуй інші літери або слово.",
            reply_markup=done_inline_keyboard()
        )
        return
    await message.answer(
        f"🔍 Знайдено по «{query}»:\nМожеш додати в список одним натисканням.",
        reply_markup=search_results_keyboard(matches)
    )


@dp.callback_query(lambda c: c.data.startswith("add_from_search:"))
async def add_from_search(callback: types.CallbackQuery):
    product = callback.data.split(":", 1)[1]
    user_id = callback.from_user.id

    if product_in_current_list(user_id, product):
        await callback.answer("ℹ️ Вже є в списку", show_alert=False)
        return

    shopping_lists.setdefault(user_id, []).append(product)
    save_data(shopping_lists, all_products)

    await callback.message.edit_text(
        f"✅ «{product}» додано до списку.\n"
        "Введи ще пошук або натисни «Готово», щоб вийти.",
        reply_markup=done_inline_keyboard()
    )
    await callback.answer()


@dp.message(lambda m: m.text == "📋 Поточний список")
async def show_list(message: types.Message):
    items = shopping_lists.get(message.from_user.id, [])

    if not items:
        await message.answer("🛒 Поточний список порожній")
        return

    text = "📝 Поточний список:\n" + "\n".join(f"• {i}" for i in items)
    await message.answer(text)


@dp.message(lambda m: m.text == "✅ Список виконано")
async def clear_list(message: types.Message):
    shopping_lists[message.from_user.id] = []
    save_data(shopping_lists, all_products)

    await message.answer("🎉 Поточний список очищено!")


# ---------- Start ----------
async def main():
    global BOT_USERNAME
    me = await bot.get_me()
    BOT_USERNAME = me.username or "bot"
    logger.info("Бот запущено: @%s", BOT_USERNAME)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

