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
class AddByText(StatesGroup):
    waiting_for_name = State()


# ---------- Bot ----------
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())
BOT_USERNAME = ""

# ---------- Data: один спільний список для всіх користувачів ----------
shopping_list, all_products = load_data()

# Останнє повідомлення з кнопкою «Вставити @бота» — щоб прибрати кнопку, коли користувач натисне іншу
_last_inline_button_msg: dict[int, tuple[int, int]] = {}  # user_id -> (chat_id, message_id)


def reload_data():
    """Перезавантажує список із файлу (щоб бачити зміни після збереження)."""
    global shopping_list, all_products
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


async def clear_last_inline_button(user_id: int):
    """Прибирає кнопку «Вставити @бота» з попереднього повідомлення."""
    if user_id not in _last_inline_button_msg:
        return
    chat_id, message_id = _last_inline_button_msg.pop(user_id, (None, None))
    if chat_id is None:
        return
    try:
        await bot.edit_message_reply_markup(
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[]),
        )
    except Exception:
        pass


# ---------- Handlers ----------
@dp.message(Command("start"))
async def start(message: types.Message, state: FSMContext):
    await state.clear()  # виходимо з режиму додавання
    await message.answer(
        "👋 <b>Вітаю!</b> Я бот для спільного списку покупок (для всієї родини).\n\n"
        "📌 <b>Що я вмію:</b>\n\n"
        "➕ <b>Додати товар</b> — натисни кнопку, потім кнопку знизу — у полі вводу зʼявиться @бот, друкуй назву. Або напиши назву товару в чат.\n\n"
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
async def add_product_prompt(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    await clear_last_inline_button(user_id)
    await state.set_state(AddByText.waiting_for_name)
    sent = await message.answer(
        "Натисни кнопку нижче — у полі вводу зʼявиться @бот, друкуй назву товару, обирай з підказок. Або напиши назву товару сюди в чат.",
        reply_markup=inline_insert_keyboard(),
    )
    _last_inline_button_msg[user_id] = (sent.chat.id, sent.message_id)


# Якщо в режимі додавання натиснули іншу кнопку або /start — виходимо з режиму, виконуємо команду
_MENU_TEXTS = ("📋 Поточний список", "✅ Список виконано", "➕ Додати товар")

@dp.message(AddByText.waiting_for_name, lambda m: m.text and m.text.strip() in _MENU_TEXTS)
async def menu_while_adding(message: types.Message, state: FSMContext):
    await state.clear()
    await clear_last_inline_button(message.from_user.id)
    if message.text == "📋 Поточний список":
        await show_list(message)
    elif message.text == "✅ Список виконано":
        await clear_list(message)
    else:
        await add_product_prompt(message, state)


@dp.message(AddByText.waiting_for_name)
async def add_product_by_text(message: types.Message, state: FSMContext):
    product = (message.text or "").strip().lower()
    if not product:
        return
    reload_data()
    if product_in_list(product):
        await clear_last_inline_button(message.from_user.id)
        sent = await message.answer(
            "ℹ️ Цей товар вже є в списку. Якщо хочеш продовжити — натисни кнопку знизу.",
            reply_markup=inline_insert_keyboard(),
        )
        _last_inline_button_msg[message.from_user.id] = (sent.chat.id, sent.message_id)
        return
    shopping_list.append(product)
    all_products.add(product)
    try:
        save_data(shopping_list, all_products)
    except Exception as e:
        logger.exception("Помилка збереження: %s", e)
        await message.answer("❌ Помилка збереження. Спробуй ще раз.", reply_markup=inline_insert_keyboard())
        return
    await clear_last_inline_button(message.from_user.id)
    sent = await message.answer(
        f"✅ Товар «{product}» додано до списку. Якщо хочеш продовжити — натисни кнопку знизу.",
        reply_markup=inline_insert_keyboard(),
    )
    _last_inline_button_msg[message.from_user.id] = (sent.chat.id, sent.message_id)


# ---------- Inline Mode ----------
def _safe_id(s: str, max_len: int = 60) -> str:
    """Унікальний id для inline результату (обмеження 64 байти)."""
    b = s.encode("utf-8")[:max_len]
    return b.decode("utf-8", errors="ignore") or "x"


@dp.inline_query()
async def inline_search(inline_query: types.InlineQuery):
    reload_data()
    q = (inline_query.query or "").strip().lower()
    results = []

    if q:
        matches = sorted(p for p in all_products if q in p)[:15]
        for i, p in enumerate(matches):
            results.append(
                InlineQueryResultArticle(
                    id=f"p:{i}",
                    title=p,
                    input_message_content=InputTextMessageContent(message_text=p),
                )
            )
        if not matches:
            results.append(
                InlineQueryResultArticle(
                    id=_safe_id(f"n:{q}"),
                    title=f"➕ Такого товару немає. Додати «{q}»?",
                    input_message_content=InputTextMessageContent(message_text=q),
                )
            )
    else:
        for i, p in enumerate(sorted(all_products)[:10]):
            results.append(
                InlineQueryResultArticle(
                    id=f"p:{i}",
                    title=p,
                    input_message_content=InputTextMessageContent(message_text=p),
                )
            )

    await inline_query.answer(results, cache_time=10)


@dp.chosen_inline_result()
async def chosen_inline(chosen: types.ChosenInlineResult):
    reload_data()
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
        all_products.add(product)  # новий товар — додаємо в «всі товари» для пошуку
    else:
        return

    user_id = chosen.from_user.id
    if product_in_list(product):
        try:
            sent = await bot.send_message(
                chat_id=user_id,
                text="ℹ️ Цей товар вже є в списку. Якщо хочеш продовжити — натисни кнопку знизу.",
                reply_markup=inline_insert_keyboard(),
            )
            _last_inline_button_msg[user_id] = (sent.chat.id, sent.message_id)
        except Exception as e:
            logger.warning("Не вдалося надіслати повідомлення: %s", e)
        return

    shopping_list.append(product)
    try:
        save_data(shopping_list, all_products)
    except Exception as e:
        logger.exception("Помилка збереження: %s", e)
        return
    logger.info("Додано товар: %s (всього в списку: %s)", product, len(shopping_list))

    try:
        sent = await bot.send_message(
            chat_id=user_id,
            text="Товар додано до списку. Якщо хочеш продовжити — натисни кнопку знизу.",
            reply_markup=inline_insert_keyboard(),
        )
        _last_inline_button_msg[user_id] = (sent.chat.id, sent.message_id)
    except Exception as e:
        logger.warning("Не вдалося надіслати повідомлення з кнопкою: %s", e)


@dp.message(lambda m: m.text == "📋 Поточний список")
async def show_list(message: types.Message):
    await clear_last_inline_button(message.from_user.id)
    reload_data()
    if not shopping_list:
        await message.answer("🛒 Список порожній")
        return
    text = "📝 Спільний список покупок:\n" + "\n".join(f"• {i}" for i in shopping_list)
    await message.answer(text)


@dp.message(lambda m: m.text == "✅ Список виконано")
async def clear_list(message: types.Message):
    await clear_last_inline_button(message.from_user.id)
    reload_data()
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
