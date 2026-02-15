import asyncio
import logging
from difflib import get_close_matches

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton
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


# ---------- Bot ----------
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())


# ---------- Data ----------
shopping_lists, all_products = load_data()


# ---------- Keyboards ----------
main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➕ Додати товар")],
        [KeyboardButton(text="📋 Поточний список")],
        [KeyboardButton(text="✅ Список виконано")]
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


def similar_products_keyboard(similar, product):
    prefix_similar = "add_similar:"
    keyboard = [
        [InlineKeyboardButton(
            text=f"➕ Додати «{p}»",
            callback_data=prefix_similar + truncate_for_callback(p, prefix_similar)
        )]
        for p in similar
    ]

    keyboard.append([
        InlineKeyboardButton(
            text=f"➕ Все одно додати «{product}»",
            callback_data="force_add"
        )
    ])

    keyboard.append([
        InlineKeyboardButton(
            text="❌ Скасувати",
            callback_data="cancel"
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


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
        "💡 Якщо назва товару схожа на ту, що ти вже додавав(ла), я запропоную варіанти — можна вибрати з списку або додати свій варіант.\n\n"
        "Команда /help — коротка підказка по кнопках.",
        parse_mode="HTML",
        reply_markup=main_keyboard
    )


@dp.message(Command("help"))
async def help_cmd(message: types.Message):
    await message.answer(
        "📖 <b>Команди та кнопки</b>\n\n"
        "➕ <b>Додати товар</b> — ввести назви товарів (можна кілька підряд).\n"
        "📋 <b>Поточний список</b> — переглянути список покупок.\n"
        "✅ <b>Список виконано</b> — очистити список після покупок.\n\n"
        "Якщо назва схожа на вже відому, бот запропонує варіанти.",
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


MENU_BUTTONS = ("➕ Додати товар", "📋 Поточний список", "✅ Список виконано")


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

    similar = get_close_matches(product, all_products, n=3, cutoff=0.7)

    if similar:
        await state.update_data(pending_product=product)
        await message.answer(
            "🤔 Можливо, ти мав(ла) на увазі:",
            reply_markup=similar_products_keyboard(similar, product)
        )
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


@dp.callback_query(lambda c: c.data.startswith("add_similar:"))
async def add_similar(callback: types.CallbackQuery, state: FSMContext):
    product = callback.data.split(":", 1)[1]
    user_id = callback.from_user.id

    if product_in_current_list(user_id, product):
        await callback.message.edit_text(
            "ℹ️ Цей товар вже є у поточному списку.",
            reply_markup=done_inline_keyboard()
        )
        await callback.answer()
        return

    shopping_lists.setdefault(user_id, []).append(product)
    save_data(shopping_lists, all_products)

    await clear_previous_done_keyboard(state, bot)
    await callback.message.edit_text(
        f"✅ «{product}» додано.\n"
        "Можеш продовжувати. Коли закінчиш — натисни «Готово» внизу.",
        reply_markup=done_inline_keyboard()
    )
    await state.update_data(
        last_done_chat_id=callback.message.chat.id,
        last_done_message_id=callback.message.message_id,
    )
    await callback.answer()


@dp.callback_query(lambda c: c.data == "force_add")
async def force_add(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    product = data.get("pending_product", "").strip()
    if not product:
        await callback.message.edit_text("❌ Сесія застаріла. Додай товар знову.")
        await callback.answer()
        return
    user_id = callback.from_user.id

    if product_in_current_list(user_id, product):
        await callback.message.edit_text(
            "ℹ️ Цей товар вже є у поточному списку.",
            reply_markup=done_inline_keyboard()
        )
        await callback.answer()
        return

    shopping_lists.setdefault(user_id, []).append(product)
    all_products.add(product)
    save_data(shopping_lists, all_products)

    await clear_previous_done_keyboard(state, bot)
    await callback.message.edit_text(
        f"✅ «{product}» додано.\n"
        "Можеш продовжувати. Коли закінчиш — натисни «Готово» внизу.",
        reply_markup=done_inline_keyboard()
    )
    await state.update_data(
        last_done_chat_id=callback.message.chat.id,
        last_done_message_id=callback.message.message_id,
    )
    await callback.answer()


@dp.callback_query(lambda c: c.data == "done")
async def done(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("👌 Режим додавання завершено")
    await callback.answer()


@dp.callback_query(lambda c: c.data == "cancel")
async def cancel(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Дію скасовано")
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
    logger.info("Бот запущено")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

