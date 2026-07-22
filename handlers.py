import logging
import httpx
import aiosqlite
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from config import API_URLS
from database import add_or_update_user, save_trophy_snapshot, get_trophy_diff_since

logger = logging.getLogger(__name__)
router = Router()

class FormStates(StatesGroup):
    waiting_tag = State()

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Brawl Stars", callback_data="game_Brawl Stars")],
            [InlineKeyboardButton(text="Clash Royale", callback_data="game_Clash Royale")],
            [InlineKeyboardButton(text="Clash of Clans", callback_data="game_Clash of Clans")]
        ]
    )
    await message.answer(
        "👋 Привет! Я помогу отслеживать прогресс трофеев в играх Supercell.\n"
        "Выберите игру, для которой хотите привязать тег:",
        reply_markup=kb
    )

@router.callback_query(F.data.startswith("game_"))
async def game_selected(callback: CallbackQuery, state: FSMContext):
    game_name = callback.data.split("_", 1)[1]
    await state.update_data(game=game_name)
    await state.set_state(FormStates.waiting_tag)
    await callback.message.delete()
    await callback.message.answer(
        f"Отлично! Теперь отправьте ваш игровой тег для **{game_name}**.\n"
        "Тег может содержать буквы, цифры, символ _ и #. Можно вводить с '#' или без.",
        parse_mode="Markdown"
    )
    await callback.answer()

@router.message(FormStates.waiting_tag)
async def handle_tag_input(message: Message, state: FSMContext):
    user_tag = message.text.strip()
    if not user_tag:
        await message.answer("Тег не может быть пустым. Введите тег ещё раз.")
        return

    if not user_tag.startswith("#"):
        user_tag = "#" + user_tag
    allowed_chars = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_#")
    user_tag = "".join(ch for ch in user_tag if ch in allowed_chars)

    data = await state.get_data()
    game_name = data.get("game")
    if not game_name:
        await message.answer("Что-то пошло не так. Попробуйте /start заново.")
        await state.clear()
        return

    api_info = API_URLS.get(game_name)
    if not api_info:
        await message.answer(f"Игра '{game_name}' не поддерживается.")
        await state.clear()
        return

    url = api_info["url"].format(user_tag.replace("#", ""))
    headers = {"Authorization": f"Bearer {api_info['key']}"}

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            data_api = resp.json()
            trophies = data_api.get("trophies")
            if trophies is None:
                await message.answer("Не удалось получить количество трофеев. Ответ API некорректен.")
                return

            await add_or_update_user(message.from_user.id, game_name, user_tag)
            await save_trophy_snapshot(game_name, user_tag, trophies)

            await message.answer(
                f"✅ Тег **{user_tag}** для **{game_name}** успешно привязан!\n"
                f"Текущие трофеи: {trophies}.\n"
                f"Теперь статистика будет собираться. Используйте /stat для просмотра.",
                parse_mode="Markdown"
            )
            await state.clear()

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 403:
                await message.answer("❌ Ошибка авторизации API (ключ недействителен). Сообщите администратору.")
            elif e.response.status_code == 404:
                await message.answer("❌ Игрок с таким тегом не найден. Проверьте правильность тега.")
            else:
                await message.answer(f"❌ Ошибка API (код {e.response.status_code}). Попробуйте позже.")
            logger.error(f"API error for tag {user_tag}: {e}")
        except Exception as e:
            await message.answer("❌ Не удалось проверить тег из-за внутренней ошибки. Повторите позже.")
            logger.exception(f"Unexpected error checking tag {user_tag}: {e}")

@router.message(Command("stat"))
async def cmd_stat(message: Message):
    async with aiosqlite.connect("bot.db") as db:
        cursor = await db.execute(
            "SELECT game_name, player_tag FROM users WHERE telegram_id = ?",
            (message.from_user.id,)
        )
        user_games = await cursor.fetchall()

    if not user_games:
        await message.answer("У вас пока нет привязанных тегов. Используйте /start, чтобы добавить.")
        return

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="1 час", callback_data="period_1")],
            [InlineKeyboardButton(text="6 часов", callback_data="period_6")],
            [InlineKeyboardButton(text="12 часов", callback_data="period_12")],
            [InlineKeyboardButton(text="24 часа", callback_data="period_24")]
        ]
    )
    await message.answer("Выберите период, за который показать изменение трофеев:", reply_markup=kb)

@router.callback_query(F.data.startswith("period_"))
async def show_stat_for_period(callback: CallbackQuery):
    hours = int(callback.data.split("_")[1])
    telegram_id = callback.from_user.id

    async with aiosqlite.connect("bot.db") as db:
        cursor = await db.execute(
            "SELECT game_name, player_tag FROM users WHERE telegram_id = ?",
            (telegram_id,)
        )
        user_games = await cursor.fetchall()

    if not user_games:
        await callback.message.edit_text("У вас нет привязанных тегов.")
        await callback.answer()
        return

    result_lines = []
    for game_name, player_tag in user_games:
        diff_info = await get_trophy_diff_since(game_name, player_tag, hours)
        if diff_info is None:
            result_lines.append(
                f"📌 **{game_name}** (`{player_tag}`): данных за {hours} час(ов) пока нет.\n"
                f"   (возможно, тег зарегистрирован недавно или не было снимков)"
            )
        else:
            diff = diff_info["diff"]
            latest = diff_info["latest_trophies"]
            old_trophies = diff_info["old_trophies"]
            old_time = diff_info["old_time"]
            result_lines.append(
                f"📊 **{game_name}** (`{player_tag}`): изменилось на **{diff:+d}** (с {old_trophies} до {latest}) "
                f"за последние {hours} час(ов) (с {old_time[:10]} {old_time[11:16]})"
            )

    if result_lines:
        await callback.message.edit_text("\n\n".join(result_lines), parse_mode="Markdown")
    else:
        await callback.message.edit_text("Не удалось получить статистику. Попробуйте позже.")
    await callback.answer()