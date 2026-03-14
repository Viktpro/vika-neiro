import asyncio
import logging
import requests
import time
import base64
import uuid
import re
import tempfile
import os
import random
from datetime import datetime
from pathlib import Path
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from database import Database
from ai_models import DeepSeekModel, OpenRouterModel, GigaChatModel

# ========== ПРОСТОЙ ВЕБ-СЕРВЕР ДЛЯ RAILWAY ==========
from aiohttp import web
import threading


async def healthcheck(request):
    return web.Response(text="Bot is running!")


async def run_web_server():
    app = web.Application()
    app.router.add_get('/', healthcheck)
    app.router.add_get('/health', healthcheck)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8080)
    await site.start()
    print("✅ Веб-сервер для Railway запущен на порту 8080")
    await asyncio.Event().wait()


def start_web_server():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(run_web_server())
    except KeyboardInterrupt:
        pass
    finally:
        loop.close()


# Запускаем веб-сервер в отдельном потоке
thread = threading.Thread(target=start_web_server, daemon=True)
thread.start()
print("✅ Веб-сервер для Railway запущен")

# ========== НАСТРОЙКИ ==========
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
if not TELEGRAM_TOKEN:
    TELEGRAM_TOKEN = "8249255843:AAE0fPLcPpmJqyWGK70xJ06mOacatNVEUgc"
    print("⚠️ Токен взят из кода (не из переменных окружения)")

CLIENT_ID = os.environ.get('CLIENT_ID', "019c9dd5-08ad-714c-8358-5945e8c15fee")
CLIENT_SECRET = os.environ.get('CLIENT_SECRET', "90a0e997-4015-458f-907a-d59f5d9e68a7")
ADMIN_IDS = [1467484237, 8249255843]  # Оба твоих ID

print(f"🔑 Токен загружен: {TELEGRAM_TOKEN[:10]}...")

# ========== ИНИЦИАЛИЗАЦИЯ ==========
admin_states = {}
db = Database()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Создаём сессию с большим таймаутом
session = AiohttpSession(
    api=TelegramAPIServer.from_base('https://api.telegram.org'),
    timeout=300
)

# Создаём бота
bot = Bot(
    token=TELEGRAM_TOKEN,
    session=session,
    default=DefaultBotProperties(parse_mode="Markdown")
)
dp = Dispatcher()

# ========== ИНИЦИАЛИЗАЦИЯ AI-МОДЕЛЕЙ ==========
giga = GigaChatModel(CLIENT_ID, CLIENT_SECRET)
deepseek = DeepSeekModel()
openrouter = OpenRouterModel()

# Хранилище выбранной модели
user_models = {}

# Словари для моделей
model_names = {
    "gigachat": "🇷🇺 GigaChat",
    "deepseek": "🇨🇳 DeepSeek",
    "mistral": "🇪🇺 Mistral",
    "llama": "🦙 Llama",
    "qwen": "🇨🇳 Qwen",
    "gemma": "🇺🇸 Gemma"
}

model_descriptions = {
    "gigachat": "🇷🇺 **GigaChat**\n• От Сбера\n• Лучший русский язык\n• Бесплатно",
    "deepseek": "🇨🇳 **DeepSeek**\n• 1 млн токенов бесплатно\n• Очень быстрый\n• Отличный код",
    "mistral": "🇪🇺 **Mistral**\n• Европейская модель\n• Открытый код\n• Хороша для логики",
    "llama": "🦙 **Llama**\n• От Meta (Facebook)\n• Самая популярная\n• 8B параметров",
    "qwen": "🇨🇳 **Qwen**\n• От Alibaba\n• 7B параметров\n• Сильная в математике",
    "gemma": "🇺🇸 **Gemma**\n• От Google\n• 9B параметров\n• Новая технология"
}

# Голос отключаем на Railway
VOICE_ENABLED = False
print("⚠️ Голосовой режим отключен для Railway")

# ========== ИНТЕРЕСНЫЕ ФАКТЫ ==========
FACTS = [
    "🧠 Язык программирования Python назван в честь комедийного шоу Monty Python, а не в честь змеи.",
    "📱 Первое SMS-сообщение было отправлено в 1992 году и содержало текст «Merry Christmas».",
    "💻 Первый компьютерный вирус был создан в 1983 году и назывался «Elk Cloner».",
    "🔍 Google изначально назывался Backrub (массаж спины).",
    "🎮 Самой продаваемой видеоигрой в истории является Minecraft.",
    "🌐 Первый веб-сайт в мире до сих пор работает: info.cern.ch",
]


# ========== ФУНКЦИЯ ПРОВЕРКИ АДМИНА ==========
def is_admin(user_id):
    return str(user_id) in [str(admin_id) for admin_id in ADMIN_IDS]


# ========== ОБРАБОТЧИКИ КОМАНД ==========

@dp.message(Command("start"))
async def start(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    last_name = message.from_user.last_name

    if not first_name:
        first_name = "друг"

    db.set_user_mode(user_id, 'general', username, first_name, last_name)

    keyboard = InlineKeyboardBuilder()
    keyboard.add(InlineKeyboardButton(text="💬 Вопрос", callback_data="mode_general"))
    keyboard.add(InlineKeyboardButton(text="👨‍💻 Код", callback_data="mode_code"))
    keyboard.add(InlineKeyboardButton(text="📚 Объяснить", callback_data="mode_explain"))
    keyboard.add(InlineKeyboardButton(text="🎨 Идеи", callback_data="mode_ideas"))
    keyboard.add(InlineKeyboardButton(text="❓ Помощь", callback_data="help"))
    keyboard.add(InlineKeyboardButton(text="📊 Статистика", callback_data="stats"))
    keyboard.add(InlineKeyboardButton(text="🤖 Выбрать модель", callback_data="model_menu"))
    keyboard.add(InlineKeyboardButton(text="📝 Заметки", callback_data="notes_menu"))

    if is_admin(user_id):
        keyboard.add(InlineKeyboardButton(text="🛠️ Админ", callback_data="admin_menu"))
        keyboard.adjust(2, 2, 2, 2, 1, 1)
    else:
        keyboard.adjust(2, 2, 2, 2, 1)

    current_model = user_models.get(user_id, "gigachat")
    model_display = model_names.get(current_model, current_model)

    await message.answer(
        f"👋 **Привет, {first_name}!**\n\n"
        f"🧠 **Нейробот Вики**\n"
        f"🤖 **Текущая модель:** {model_display}\n\n"
        f"👇 **Выбери режим:**",
        parse_mode="Markdown",
        reply_markup=keyboard.as_markup()
    )


@dp.message(Command("model"))
async def model_command(message: types.Message):
    keyboard = InlineKeyboardBuilder()
    keyboard.add(InlineKeyboardButton(text="🇷🇺 GigaChat", callback_data="model_gigachat"))
    keyboard.add(InlineKeyboardButton(text="🇨🇳 DeepSeek", callback_data="model_deepseek"))
    keyboard.add(InlineKeyboardButton(text="🇪🇺 Mistral", callback_data="model_mistral"))
    keyboard.add(InlineKeyboardButton(text="🦙 Llama", callback_data="model_llama"))
    keyboard.add(InlineKeyboardButton(text="🇨🇳 Qwen", callback_data="model_qwen"))
    keyboard.add(InlineKeyboardButton(text="🇺🇸 Gemma", callback_data="model_gemma"))
    keyboard.adjust(2, 2, 2)

    current_model = user_models.get(message.from_user.id, "gigachat")
    current_display = model_names.get(current_model, current_model)

    text = f"🤖 **Выбери AI-модель:**\n\n"
    text += f"🔹 **Сейчас выбрана:** {current_display}\n\n"
    text += "**Что умеют модели:**\n\n"

    for model_key, desc in model_descriptions.items():
        if model_key == current_model:
            text += f"⭐ {desc} (текущая)\n\n"
        else:
            text += f"• {desc}\n\n"

    await message.answer(text, parse_mode="Markdown", reply_markup=keyboard.as_markup())


@dp.message(Command("help"))
async def help_command(message: types.Message):
    await message.answer(
        "🤖 **Доступные команды:**\n\n"
        "📌 **Основные:**\n"
        "/start - Главное меню\n"
        "/help - Эта справка\n"
        "/stats - Твоя статистика\n"
        "/clear - Сбросить диалог\n\n"
        "📝 **Заметки:**\n"
        "/note текст - сохранить заметку\n"
        "/notes - показать заметки\n"
        "/delnote номер - удалить заметку\n\n"
        "🤖 **AI-модели:**\n"
        "/model - Выбрать нейросеть\n\n"
        "🔧 **Полезные:**\n"
        "/time - Текущее время\n"
        "/random - Случайное число\n"
        "/fact - Интересный факт",
        parse_mode="Markdown"
    )


@dp.message(Command("time"))
async def time_command(message: types.Message):
    now = datetime.now()
    await message.answer(
        f"📅 **Сегодня:** {now.strftime('%d.%m.%Y')}\n"
        f"⏰ **Точное время:** {now.strftime('%H:%M:%S')}",
        parse_mode="Markdown"
    )


@dp.message(Command("random"))
async def random_command(message: types.Message):
    number = random.randint(1, 100)
    await message.answer(f"🎲 **Случайное число:** {number}", parse_mode="Markdown")


@dp.message(Command("fact"))
async def fact_command(message: types.Message):
    fact = random.choice(FACTS)
    await message.answer(f"🔮 **Интересный факт:**\n\n{fact}", parse_mode="Markdown")


@dp.message(Command("stats"))
async def stats_command(message: types.Message):
    stats = db.get_user_stats(message.from_user.id)
    await message.answer(
        f"📊 **Твоя статистика:**\n\n"
        f"• Сообщений: {stats['messages']}\n"
        f"• 👍 Лайков: {stats['likes']}\n"
        f"• 👎 Дизлайков: {stats['dislikes']}",
        parse_mode="Markdown"
    )


@dp.message(Command("clear"))
async def clear_command(message: types.Message):
    await message.answer("✅ Диалог сброшен. /start")


@dp.message(Command("cancel"))
async def cancel_command(message: types.Message):
    user_id = message.from_user.id
    cancelled = False

    for key in list(admin_states.keys()):
        if admin_states[key] == user_id:
            del admin_states[key]
            cancelled = True

    if cancelled:
        await message.answer("✅ Действие отменено. /start")
    else:
        await message.answer("❌ Нет активных действий для отмены")


# ========== ЗАМЕТКИ ==========

@dp.message(Command("note"))
async def note_command(message: types.Message):
    text = message.text.replace("/note", "", 1).strip()
    if not text:
        await message.answer(
            "📝 **Как пользоваться заметками:**\n\n"
            "/note текст - сохранить заметку\n"
            "/notes - показать заметки\n"
            "/delnote номер - удалить заметку",
            parse_mode="Markdown"
        )
        return

    user_id = message.from_user.id
    note_id = db.save_note(user_id, text)

    await message.answer(
        f"✅ **Заметка сохранена!**\n\n"
        f"📝 {text}\n\n"
        f"📌 Номер: {note_id}",
        parse_mode="Markdown"
    )


@dp.message(Command("notes"))
async def notes_command(message: types.Message):
    user_id = message.from_user.id
    notes = db.get_notes(user_id)

    if not notes:
        await message.answer(
            "📭 **У тебя пока нет заметок**\n\n"
            "/note текст - создать заметку",
            parse_mode="Markdown"
        )
        return

    text = "📝 **Твои заметки:**\n\n"
    for note in notes[:10]:
        text += f"📌 {note['note']}\n"
        text += f"   🆔 {note['id']}\n\n"

    await message.answer(text, parse_mode="Markdown")


@dp.message(Command("delnote"))
async def delnote_command(message: types.Message):
    args = message.text.split()
    if len(args) < 2:
        await message.answer("❌ **Укажи номер заметки**\n\nПример: /delnote 5", parse_mode="Markdown")
        return

    try:
        note_id = int(args[1])
        user_id = message.from_user.id

        if db.delete_note(note_id, user_id):
            await message.answer(f"✅ **Заметка {note_id} удалена**", parse_mode="Markdown")
        else:
            await message.answer(f"❌ **Заметка {note_id} не найдена**", parse_mode="Markdown")
    except ValueError:
        await message.answer("❌ **Номер должен быть числом**", parse_mode="Markdown")


# ========== ОБРАБОТЧИК КНОПОК ==========

@dp.callback_query()
async def callback_handler(callback: types.CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id
    username = callback.from_user.username
    first_name = callback.from_user.first_name
    last_name = callback.from_user.last_name

    # Возврат в главное меню
    if callback.data == "back_to_main":
        await start(callback.message)
        return

    # Меню заметок
    if callback.data == "notes_menu":
        keyboard = InlineKeyboardBuilder()
        keyboard.add(InlineKeyboardButton(text="📝 Показать заметки", callback_data="notes_show"))
        keyboard.add(InlineKeyboardButton(text="➕ Добавить заметку", callback_data="notes_add"))
        keyboard.add(InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main"))
        keyboard.adjust(1)

        await callback.message.edit_text(
            "📝 **Записной блокнот**\n\n"
            "Здесь ты можешь хранить свои заметки.",
            parse_mode="Markdown",
            reply_markup=keyboard.as_markup()
        )
        return

    if callback.data == "notes_show":
        await notes_command(callback.message)
        return

    if callback.data == "notes_add":
        await callback.message.answer(
            "📝 **Напиши текст заметки**\n"
            "Используй команду /note текст",
            parse_mode="Markdown"
        )
        return

    # Меню выбора модели
    if callback.data == "model_menu":
        await model_command(callback.message)
        return

    # Выбор модели
    if callback.data.startswith("model_"):
        model = callback.data.replace("model_", "")
        user_models[user_id] = model
        await callback.message.answer(
            f"✅ **Модель переключена на {model_names.get(model, model)}**",
            parse_mode="Markdown"
        )
        return

    # Выбор режима
    if callback.data.startswith("mode_"):
        mode = callback.data.replace("mode_", "")
        db.set_user_mode(user_id, mode, username, first_name, last_name)
        await callback.message.answer(
            f"✅ **Режим «{mode}» активирован!**",
            parse_mode="Markdown"
        )
        return

    # Помощь
    if callback.data == "help":
        await help_command(callback.message)
        return

    # Статистика
    if callback.data == "stats":
        stats = db.get_user_stats(user_id)
        await callback.message.answer(
            f"📊 **Твоя статистика:**\n\n"
            f"• Сообщений: {stats['messages']}\n"
            f"• 👍 Лайков: {stats['likes']}\n"
            f"• 👎 Дизлайков: {stats['dislikes']}\n\n"
            f"Всего пользователей: {db.get_all_users_count()}",
            parse_mode="Markdown"
        )
        return

    # Админ-меню (упрощенно)
    if is_admin(user_id) and callback.data == "admin_menu":
        prompts = db.get_all_prompts()
        text = "📋 **Системные промпты:**\n\n"
        for mode, prompt in prompts.items():
            text += f"• **{mode}**: {prompt[:50]}...\n\n"
        await callback.message.answer(text, parse_mode="Markdown")
        return


# ========== ОСНОВНОЙ ОБРАБОТЧИК ТЕКСТА ==========

@dp.message()
async def handle_message(message: types.Message):
    user_id = message.from_user.id

    # Проверяем админские состояния (для создания промптов)
    if is_admin(user_id):
        if 'awaiting_mode_name' in admin_states:
            mode_name = message.text.strip().lower().replace(' ', '_')
            admin_states['new_mode_name'] = mode_name
            admin_states.pop('awaiting_mode_name')
            admin_states['awaiting_mode_prompt'] = user_id
            await message.answer(f"✅ Название: **{mode_name}**\n\nТеперь отправь текст промпта:", parse_mode="Markdown")
            return

        if 'awaiting_mode_prompt' in admin_states:
            mode_name = admin_states.get('new_mode_name')
            if db.add_prompt(mode_name, message.text):
                await message.answer(f"✅ Режим **{mode_name}** создан!")
            else:
                await message.answer("❌ Ошибка: режим уже существует")
            admin_states.pop('awaiting_mode_prompt', None)
            admin_states.pop('new_mode_name', None)
            return

        for mode, admin_id in list(admin_states.items()):
            if admin_id == user_id and mode not in ['awaiting_mode_name', 'awaiting_mode_prompt']:
                if db.update_prompt(mode, message.text):
                    await message.answer(f"✅ Промпт для **{mode}** обновлён!")
                else:
                    await message.answer("❌ Ошибка при обновлении")
                admin_states.pop(mode)
                return

    # Получаем режим и промпт
    mode = db.get_user_mode(user_id)
    system_prompt = db.get_prompt(mode) or "Ты полезный ассистент."
    db.save_message(user_id, 'user', message.text, mode)

    await message.bot.send_chat_action(message.chat.id, action="typing")

    # Выбираем модель
    user_model = user_models.get(user_id, "gigachat")

    try:
        if user_model == "gigachat":
            response = giga.ask(message.text, system_prompt)
        elif user_model == "deepseek":
            response = deepseek.ask(message.text, system_prompt)
        elif user_model in ["mistral", "llama", "qwen", "gemma"]:
            response = openrouter.ask(message.text, model=user_model, system_prompt=system_prompt)
        else:
            response = giga.ask(message.text, system_prompt)
    except Exception as e:
        response = f"❌ Ошибка AI: {str(e)}"

    message_id = db.save_message(user_id, 'assistant', response, mode)

    # Кнопки оценки
    keyboard = InlineKeyboardBuilder()
    keyboard.add(InlineKeyboardButton(text="👍", callback_data=f"like_{message_id}"))
    keyboard.add(InlineKeyboardButton(text="👎", callback_data=f"dislike_{message_id}"))

    await message.answer(response, parse_mode="Markdown", reply_markup=keyboard.as_markup())


# ========== ЗАПУСК ==========

async def main():
    logger.info("🚀 Бот запущен!")
    logger.info(f"🎤 Голосовой режим: ВЫКЛЮЧЕН")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())