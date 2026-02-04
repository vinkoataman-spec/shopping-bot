import asyncio
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
from data_meneger import load_data, save_data
import os

BOT_TOKEN = os.getenv("BOT_TOKEN")


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


def similar_products_keyboard(similar, product):
    keyboard = [
        [InlineKeyboardButton(
            text=f"➕ Додати «{p}»",
            callback_data=f"add_similar:{p}"
        )]
        for p in similar
    ]

    keyboard.append([
        InlineKeyboardButton(
            text=f"➕ Все одно додати «{product}»",
            callback_data=f"force_add:{product}"
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
        "👋 Вітаю!\n"
        "Я допоможу вести поточний список покупок.",
        reply_markup=main_keyboard
    )


@dp.message(lambda m: m.text == "➕ Додати товар")
async def start_add(message: types.Message, state: FSMContext):
    await state.set_state(AddProduct.waiting_for_product)
    await message.answer(
        "✍️ Напиши назву товару.\n"
        "Можеш надсилати кілька повідомлень підряд.",
        reply_markup=done_inline_keyboard()
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
        await message.answer(
            "🤔 Можливо, ти мав(ла) на увазі:",
            reply_markup=similar_products_keyboard(similar, product)
        )
        return

    shopping_lists.setdefault(user_id, []).append(product)
    all_products.add(product)
    save_data(shopping_lists, all_products)

    await message.answer(
        f"✅ «{product}» додано.\n"
        "Можеш продовжувати.",
        reply_markup=done_inline_keyboard()
    )


@dp.callback_query(lambda c: c.data.startswith("add_similar:"))
async def add_similar(callback: types.CallbackQuery):
    product = callback.data.split(":")[1]
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

    await callback.message.edit_text(
        f"✅ «{product}» додано.\n"
        "Можеш продовжувати.",
        reply_markup=done_inline_keyboard()
    )
    await callback.answer()


@dp.callback_query(lambda c: c.data.startswith("force_add:"))
async def force_add(callback: types.CallbackQuery):
    product = callback.data.split(":")[1]
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

    await callback.message.edit_text(
        f"✅ «{product}» додано.\n"
        "Можеш продовжувати.",
        reply_markup=done_inline_keyboard()
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
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

