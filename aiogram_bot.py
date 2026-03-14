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
from aiohttp import web  # Добавляем для веб-сервера
from database import Database
from ai_models import DeepSeekModel, OpenRouterModel, GigaChatModel

# ========== НАСТРОЙКИ ДЛЯ RENDER ==========
# Определяем, запущены ли мы на Render
IS_RENDER = os.environ.get('RENDER') is not None

if IS_RENDER:
    # Настройки для Render
    PORT = int(os.environ.get('PORT', 10000))

    # Получаем домен Render
    RENDER_EXTERNAL_URL = os.environ.get('RENDER_EXTERNAL_URL')
    if RENDER_EXTERNAL_URL:
        PUBLIC_DOMAIN = RENDER_EXTERNAL_URL.replace('https://', '')
    else:
        PUBLIC_DOMAIN = os.environ.get('RENDER_PUBLIC_DOMAIN', 'localhost')

    print(f"🚀 Запуск на Render: {PUBLIC_DOMAIN}:{PORT}")
else:
    # Локальный запуск
    PORT = 8080
    PUBLIC_DOMAIN = 'localhost'
    print("💻 Локальный запуск")

# ========== ГОЛОСОВЫЕ МОДУЛИ ==========
try:
    from voice.stt import STT
    from voice.tts import TTS

    VOICE_ENABLED = True
except ImportError as e:
    print(f"⚠️ Голосовые модули не загружены: {e}")
    VOICE_ENABLED = False

# ========== НАСТРОЙКИ ==========
TELEGRAM_TOKEN = "8249255843:AAE0fPLcPpmJqyWGK70xJ06mOacatNVEUgc"
CLIENT_ID = "019c9dd5-08ad-714c-8358-5945e8c15fee"
CLIENT_SECRET = "90a0e997-4015-458f-907a-d59f5d9e68a7"
ADMIN_IDS = [1467484237, 8249255843]  # Оба твоих ID

# ========== ИНИЦИАЛИЗАЦИЯ ==========
admin_states = {}
db = Database()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Создаём сессию с большим таймаутом для стабильности
session = AiohttpSession(
    api=TelegramAPIServer.from_base('https://api.telegram.org'),
    timeout=300  # Увеличенный таймаут до 5 минут
)

# Создаём бота с этой сессией
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

# Хранилище выбранной модели для каждого пользователя
user_models = {}

# Словарь с названиями моделей для красивого отображения
model_names = {
    "gigachat": "🇷🇺 GigaChat",
    "deepseek": "🇨🇳 DeepSeek",
    "mistral": "🇪🇺 Mistral",
    "llama": "🦙 Llama",
    "qwen": "🇨🇳 Qwen",
    "gemma": "🇺🇸 Gemma"
}

# Словарь с описаниями моделей
model_descriptions = {
    "gigachat": "🇷🇺 **GigaChat**\n• От Сбера\n• Лучший русский язык\n• Бесплатно\n• Поддерживает картинки",
    "deepseek": "🇨🇳 **DeepSeek**\n• 1 млн токенов бесплатно\n• Очень быстрый\n• Отличный код\n• Китайская модель",
    "mistral": "🇪🇺 **Mistral**\n• Европейская модель\n• Открытый код\n• Хороша для логики\n• 7B параметров",
    "llama": "🦙 **Llama**\n• От Meta (Facebook)\n• Самая популярная\n• 8B параметров\n• Много языков",
    "qwen": "🇨🇳 **Qwen**\n• От Alibaba\n• 7B параметров\n• Сильная в математике\n• Поддерживает код",
    "gemma": "🇺🇸 **Gemma**\n• От Google\n• 9B параметров\n• Новая технология\n• Быстрая"
}

# Инициализация голосовых модулей
if VOICE_ENABLED:
    try:
        stt = STT()
        tts = TTS()
        logger.info("✅ Голосовые модули инициализированы")
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации голосовых модулей: {e}")
        VOICE_ENABLED = False

# ========== ИНТЕРЕСНЫЕ ФАКТЫ ==========
FACTS = [
    "🧠 Язык программирования Python назван в честь комедийного шоу Monty Python, а не в честь змеи.",
    "📱 Первое SMS-сообщение было отправлено в 1992 году и содержало текст «Merry Christmas».",
    "💻 Первый компьютерный вирус был создан в 1983 году и назывался «Elk Cloner».",
    "🔍 Google изначально назывался Backrub (массаж спины).",
    "🎮 Самой продаваемой видеоигрой в истории является Minecraft.",
    "🌐 Первый веб-сайт в мире до сих пор работает: info.cern.ch",
    "📊 Более 90% всех данных в мире было создано за последние 2 года.",
    "⚡ Скорость загрузки интернета на Марсе составляет всего 500 кбит/с.",
    "🧮 Первый жесткий диск весил больше тонны и хранил всего 5 МБ данных.",
    "📧 Символ @ в email называется «собачкой» только в России.",
]


# ========== ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ ==========
def is_admin(user_id):
    """Проверяет, является ли пользователь админом"""
    return str(user_id) in [str(admin_id) for admin_id in ADMIN_IDS]


# ========== ОБРАБОТЧИКИ ==========

@dp.message(Command("start"))
async def start(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    last_name = message.from_user.last_name

    # Если нет имени, используем "друг"
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

    voice_status = "🎤 Голосовой ввод активен" if VOICE_ENABLED else "⚠️ Голосовой режим недоступен"

    current_model = user_models.get(user_id, "gigachat")
    model_display = model_names.get(current_model, current_model)

    await message.answer(
        f"👋 **Привет, {first_name}!**\n\n"
        f"🧠 **Главное меню Нейробота Вики**\n"
        f"🤖 **Текущая модель:** {model_display}\n\n"
        f"👇 **Выбери режим:**\n"
        f"_{voice_status}_",
        parse_mode="Markdown",
        reply_markup=keyboard.as_markup()
    )


# ========== ЗАПИСНОЙ БЛОКНОТ ==========

@dp.message(Command("note"))
async def note_command(message: types.Message):
    """Добавить заметку"""
    text = message.text.replace("/note", "", 1).strip()
    if not text:
        await message.answer(
            "📝 **Как пользоваться заметками:**\n\n"
            "/note текст - сохранить заметку\n"
            "/notes - показать все заметки\n"
            "/delnote номер - удалить заметку\n\n"
            "Пример: /note Купить молоко",
            parse_mode="Markdown"
        )
        return

    user_id = message.from_user.id
    note_id = db.save_note(user_id, text)

    await message.answer(
        f"✅ **Заметка сохранена!**\n\n"
        f"📝 `{text}`\n\n"
        f"📌 Номер заметки: {note_id}\n"
        f"Используй /notes чтобы увидеть все",
        parse_mode="Markdown"
    )


@dp.message(Command("notes"))
async def notes_command(message: types.Message):
    """Показать все заметки"""
    user_id = message.from_user.id
    notes = db.get_notes(user_id)

    if not notes:
        await message.answer(
            "📭 **У тебя пока нет заметок**\n\n"
            "Чтобы создать заметку, напиши:\n"
            "/note твой текст",
            parse_mode="Markdown"
        )
        return

    text = "📝 **Твои заметки:**\n\n"
    for i, note in enumerate(notes[:20], 1):
        created = note['created_at'][:16] if note['created_at'] else ""
        text += f"{i}. `{note['note']}`\n"
        text += f"   🆔 {note['id']} | {created}\n\n"

    text += "\n_Удалить заметку: /delnote номер_"

    # Разбиваем, если слишком длинное сообщение
    if len(text) > 4000:
        for chunk in [text[i:i + 4000] for i in range(0, len(text), 4000)]:
            await message.answer(chunk, parse_mode="Markdown")
    else:
        await message.answer(text, parse_mode="Markdown")


@dp.message(Command("delnote"))
async def delnote_command(message: types.Message):
    """Удалить заметку по ID"""
    args = message.text.split()
    if len(args) < 2:
        await message.answer(
            "❌ **Укажи номер заметки**\n\n"
            "Пример: /delnote 5\n"
            "Номер можно узнать через /notes",
            parse_mode="Markdown"
        )
        return

    try:
        note_id = int(args[1])
        user_id = message.from_user.id

        # Проверяем, что заметка принадлежит пользователю
        if db.delete_note(note_id, user_id):
            await message.answer(f"✅ **Заметка {note_id} удалена**", parse_mode="Markdown")
        else:
            await message.answer(
                f"❌ **Заметка {note_id} не найдена**\n\n"
                f"Убедись, что номер правильный",
                parse_mode="Markdown"
            )
    except ValueError:
        await message.answer("❌ **Номер должен быть числом**", parse_mode="Markdown")


@dp.callback_query(lambda c: c.data == "notes_menu")
async def notes_menu_callback(callback: types.CallbackQuery):
    """Меню заметок"""
    keyboard = InlineKeyboardBuilder()
    keyboard.add(InlineKeyboardButton(text="📝 Показать заметки", callback_data="notes_show"))
    keyboard.add(InlineKeyboardButton(text="➕ Добавить заметку", callback_data="notes_add"))
    keyboard.add(InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main"))
    keyboard.adjust(1)

    await callback.message.edit_text(
        "📝 **Записной блокнот**\n\n"
        "Здесь ты можешь хранить свои заметки.\n"
        "Они сохраняются в базе данных и не пропадают после перезапуска бота.",
        parse_mode="Markdown",
        reply_markup=keyboard.as_markup()
    )


@dp.callback_query(lambda c: c.data == "notes_show")
async def notes_show_callback(callback: types.CallbackQuery):
    """Показать заметки через кнопку"""
    await callback.answer()
    await notes_command(callback.message)


@dp.callback_query(lambda c: c.data == "notes_add")
async def notes_add_callback(callback: types.CallbackQuery):
    """Добавить заметку через кнопку"""
    await callback.answer()
    await callback.message.answer(
        "📝 **Напиши текст заметки**\n"
        "Например: Купить молоко и хлеб\n\n"
        "Используй команду /note текст",
        parse_mode="Markdown"
    )


# ========== ОСТАЛЬНЫЕ ОБРАБОТЧИКИ (админка, модель, статистика и т.д.) ==========

@dp.message(Command("admin"))
async def admin_menu(message: types.Message):
    user_id = message.from_user.id

    if not is_admin(user_id):
        await message.answer(f"⛔ У вас нет прав администратора. Ваш ID: {user_id}")
        return

    keyboard = InlineKeyboardBuilder()
    keyboard.add(InlineKeyboardButton(text="📋 Список промптов", callback_data="admin_list"))
    keyboard.add(InlineKeyboardButton(text="✏️ Редактировать", callback_data="admin_edit_menu"))
    keyboard.add(InlineKeyboardButton(text="➕ Новый режим", callback_data="admin_add"))
    keyboard.add(InlineKeyboardButton(text="❌ Удалить режим", callback_data="admin_delete"))
    keyboard.add(InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main"))
    keyboard.adjust(2, 2, 1)

    voice_status = "✅ Голосовой модуль работает" if VOICE_ENABLED else "❌ Голосовой модуль отключен"

    await message.answer(
        f"🛠️ **Панель администратора**\n\n{voice_status}",
        parse_mode="Markdown",
        reply_markup=keyboard.as_markup()
    )


@dp.message(Command("model"))
async def model_command(message: types.Message):
    """Выбор AI-модели с описаниями"""
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
            text += f"⭐ **{desc}** (текущая)\n\n"
        else:
            text += f"• {desc}\n\n"

    text += "_Нажми на кнопку, чтобы выбрать модель_"

    await message.answer(
        text,
        parse_mode="Markdown",
        reply_markup=keyboard.as_markup()
    )


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


@dp.message(Command("time"))
async def time_command(message: types.Message):
    """Показывает текущую дату и время"""
    now = datetime.now()
    await message.answer(
        f"📅 **Сегодня:** {now.strftime('%d.%m.%Y')}\n"
        f"⏰ **Точное время:** {now.strftime('%H:%M:%S')}",
        parse_mode="Markdown"
    )


@dp.message(Command("random"))
async def random_command(message: types.Message):
    """Генерирует случайное число"""
    args = message.text.split()
    if len(args) == 3:
        try:
            min_num = int(args[1])
            max_num = int(args[2])
            number = random.randint(min_num, max_num)
            await message.answer(f"🎲 **Случайное число от {min_num} до {max_num}:** {number}")
        except:
            await message.answer("❌ Используй: /random мин макс")
    else:
        number = random.randint(1, 100)
        await message.answer(f"🎲 **Случайное число:** {number}")


@dp.message(Command("fact"))
async def fact_command(message: types.Message):
    """Показывает случайный интересный факт"""
    fact = random.choice(FACTS)
    await message.answer(f"🔮 **Интересный факт:**\n\n{fact}", parse_mode="Markdown")


@dp.message(Command("help"))
async def help_command(message: types.Message):
    """Показывает список всех команд"""
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
        "/fact - Интересный факт\n\n"
        "🎤 **Голосовой режим:**\n"
        "/voice_ru - Русский голос\n"
        "/voice_en - Английский голос\n"
        "Или просто отправь голосовое сообщение!",
        parse_mode="Markdown"
    )


@dp.message(Command("cancel"))
async def cancel_command(message: types.Message):
    """Отменяет текущее действие"""
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


@dp.message(Command("voice_ru"))
async def voice_ru(message: types.Message):
    """Русский голос"""
    if VOICE_ENABLED:
        tts.set_language('ru')
        await message.answer("✅ Голос переключён на **русский**", parse_mode="Markdown")
    else:
        await message.answer("❌ Голосовой режим недоступен")


@dp.message(Command("voice_en"))
async def voice_en(message: types.Message):
    """Английский голос"""
    if VOICE_ENABLED:
        tts.set_language('en')
        await message.answer("✅ Голос переключён на **английский**", parse_mode="Markdown")
    else:
        await message.answer("❌ Голосовой режим недоступен")


@dp.callback_query()
async def callback_handler(callback: types.CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id
    username = callback.from_user.username
    first_name = callback.from_user.first_name
    last_name = callback.from_user.last_name

    # Лайки
    if callback.data.startswith(('like_', 'dislike_')):
        parts = callback.data.split('_')
        rating = 1 if parts[0] == 'like' else -1
        message_id = int(parts[1])
        db.save_feedback(user_id, message_id, rating)
        await callback.message.edit_text(
            callback.message.text.replace("\n\n_Оцени ответ, пожалуйста:_", ""),
            parse_mode="Markdown"
        )
        return

    # Возврат в главное меню
    if callback.data == "back_to_main":
        await start(callback.message)
        return

    # Меню заметок
    if callback.data == "notes_menu":
        await notes_menu_callback(callback)
        return

    # Меню выбора модели
    if callback.data == "model_menu":
        await model_command(callback.message)
        return

    # Выбор модели с подтверждением
    if callback.data.startswith("model_"):
        model = callback.data.replace("model_", "")
        user_models[user_id] = model

        await callback.message.answer(
            f"✅ **Модель успешно переключена!**\n\n"
            f"Теперь выбрана: **{model_names.get(model, model)}**\n\n"
            f"🔹 **GigaChat** - лучший русский язык\n"
            f"🔹 **DeepSeek** - быстрый, бесплатный\n"
            f"🔹 **Mistral** - отличная логика\n"
            f"🔹 **Llama** - самая популярная\n"
            f"🔹 **Qwen** - сильная в математике\n"
            f"🔹 **Gemma** - от Google",
            parse_mode="Markdown"
        )
        return

    # Режимы
    if callback.data.startswith("mode_"):
        mode = callback.data.replace("mode_", "")
        db.set_user_mode(user_id, mode, username, first_name, last_name)
        await callback.message.answer(
            f"✅ **Режим «{mode}» активирован!**\n\n"
            f"Теперь напиши свой вопрос или отправь голосовое сообщение.",
            parse_mode="Markdown"
        )
        return

    # Админ-меню
    if is_admin(user_id):
        if callback.data == "admin_menu":
            await admin_menu(callback.message)
            return

        if callback.data == "admin_list":
            prompts = db.get_all_prompts()
            text = "📋 **Системные промпты:**\n\n"
            for mode, prompt in prompts.items():
                short_prompt = prompt[:100] + "..." if len(prompt) > 100 else prompt
                text += f"• **{mode}**: {short_prompt}\n\n"
            await callback.message.edit_text(
                text,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")]])
            )
            return

        if callback.data == "admin_edit_menu":
            prompts = db.get_all_prompts()
            keyboard = InlineKeyboardBuilder()
            for mode in prompts.keys():
                keyboard.add(InlineKeyboardButton(text=f"✏️ {mode}", callback_data=f"admin_edit_{mode}"))
            keyboard.add(InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back"))
            keyboard.adjust(2)
            await callback.message.edit_text(
                "✏️ **Выбери режим для редактирования:**",
                parse_mode="Markdown",
                reply_markup=keyboard.as_markup()
            )
            return

        if callback.data.startswith("admin_edit_"):
            mode = callback.data.replace("admin_edit_", "")
            current_prompt = db.get_prompt(mode)
            admin_states[mode] = user_id
            await callback.message.edit_text(
                f"✏️ **Редактирование режима «{mode}»**\n\n"
                f"Текущий промпт:\n```\n{current_prompt}\n```\n\n"
                f"📝 Отправь новый текст промпта в ответ на это сообщение.\n\n"
                f"🚫 Для отмены отправь /cancel",
                parse_mode="Markdown"
            )
            return

        if callback.data == "admin_add":
            await callback.message.edit_text(
                "➕ **Создание нового режима**\n\n"
                "Отправь название режима (одно слово, латиницей):\n"
                "Например: `poetry`\n\n"
                "🚫 Для отмены отправь /cancel",
                parse_mode="Markdown"
            )
            admin_states['awaiting_mode_name'] = user_id
            return

        if callback.data == "admin_delete":
            prompts = db.get_all_prompts()
            keyboard = InlineKeyboardBuilder()
            for mode in prompts.keys():
                keyboard.add(InlineKeyboardButton(text=f"❌ {mode}", callback_data=f"admin_del_{mode}"))
            keyboard.add(InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back"))
            keyboard.adjust(2)
            await callback.message.edit_text(
                "❌ **Выбери режим для удаления:**",
                parse_mode="Markdown",
                reply_markup=keyboard.as_markup()
            )
            return

        if callback.data.startswith("admin_del_"):
            mode = callback.data.replace("admin_del_", "")
            keyboard = InlineKeyboardBuilder()
            keyboard.add(InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"admin_confirm_del_{mode}"))
            keyboard.add(InlineKeyboardButton(text="❌ Нет, отмена", callback_data="admin_back"))
            await callback.message.edit_text(
                f"❓ **Точно удалить режим «{mode}»?**",
                parse_mode="Markdown",
                reply_markup=keyboard.as_markup()
            )
            return

        if callback.data.startswith("admin_confirm_del_"):
            mode = callback.data.replace("admin_confirm_del_", "")
            if db.delete_prompt(mode):
                await callback.message.edit_text(
                    f"✅ Режим «{mode}» удалён.",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                        InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")
                    ]])
                )
            else:
                await callback.message.edit_text(f"❌ Ошибка при удалении режима «{mode}».")
            return

        if callback.data == "admin_back":
            await admin_menu(callback.message)
            return

    # Обычные кнопки
    if callback.data == "help":
        await help_command(callback.message)
    elif callback.data == "stats":
        stats = db.get_user_stats(user_id)
        await callback.message.answer(
            f"📊 **Твоя статистика:**\n\n"
            f"• Сообщений: {stats['messages']}\n"
            f"• 👍 Лайков: {stats['likes']}\n"
            f"• 👎 Дизлайков: {stats['dislikes']}\n\n"
            f"Всего пользователей: {db.get_all_users_count()}",
            parse_mode="Markdown"
        )


# ========== ОБРАБОТЧИК ГОЛОСОВЫХ СООБЩЕНИЙ ==========
@dp.message(lambda message: message.voice is not None)
async def voice_message_handler(message: types.Message):
    """Обработчик голосовых сообщений"""

    if not VOICE_ENABLED:
        await message.answer("❌ Голосовой режим временно недоступен. Отправь текст.")
        return

    user_id = message.from_user.id
    logger.info(f"🎤 Получено голосовое сообщение от пользователя {user_id}")

    # Проверяем режим пользователя
    mode = db.get_user_mode(user_id)
    system_prompt = db.get_prompt(mode) or "Ты полезный ассистент."

    # Показываем статус
    status_msg = await message.answer("🎤 Распознаю речь...")

    temp_files = []

    try:
        # Скачиваем голосовое сообщение с повторными попытками
        logger.info("📥 Скачиваю голосовой файл...")
        max_retries = 3
        for attempt in range(max_retries):
            try:
                file = await message.bot.get_file(message.voice.file_id)

                with tempfile.NamedTemporaryFile(suffix='.ogg', delete=False) as tmp_file:
                    await message.bot.download_file(file.file_path, tmp_file.name)
                    ogg_path = tmp_file.name
                    temp_files.append(ogg_path)
                    logger.info(f"✅ Файл скачан: {ogg_path}")
                    break
            except Exception as e:
                logger.warning(f"⚠️ Попытка {attempt + 1}/{max_retries} не удалась: {e}")
                if attempt == max_retries - 1:
                    raise
                await asyncio.sleep(2)

        # Преобразуем речь в текст
        await status_msg.edit_text("🔄 Преобразую речь в текст...")
        logger.info("🎤 Запускаю распознавание речи...")

        recognized_text = stt.audio_to_text(ogg_path)
        logger.info(f"📝 Распознано: {recognized_text}")

        if recognized_text.startswith("❌") or recognized_text.startswith("🔇"):
            await status_msg.edit_text(recognized_text)
            return

        # Показываем распознанный текст
        await status_msg.edit_text(
            f"📝 **Распознано:**\n{recognized_text}\n\n"
            f"🤔 Думаю...",
            parse_mode="Markdown"
        )

        # Сохраняем сообщение пользователя
        db.save_message(user_id, 'user', f"[голосовое] {recognized_text}", mode)

        # Получаем ответ от выбранной AI-модели
        logger.info("🤖 Отправляю запрос в AI-модель...")

        user_model = user_models.get(user_id, "gigachat")

        if user_model == "gigachat":
            response = giga.ask(recognized_text, system_prompt)
        elif user_model == "deepseek":
            response = deepseek.ask(recognized_text, system_prompt)
        elif user_model in ["mistral", "llama", "qwen", "gemma"]:
            response = openrouter.ask(recognized_text, model=user_model, system_prompt=system_prompt)
        else:
            response = giga.ask(recognized_text, system_prompt)

        logger.info(f"✅ Ответ получен, длина: {len(response)} символов")

        # Сохраняем ответ бота
        message_id = db.save_message(user_id, 'assistant', response, mode)

        # Создаём голосовой ответ
        await status_msg.edit_text("🔊 Создаю голосовой ответ...")
        logger.info("🔊 Генерирую голос через TTS...")

        # Создаём временный файл для голосового ответа
        with tempfile.NamedTemporaryFile(suffix='.ogg', delete=False) as tmp_file:
            output_path = tmp_file.name
            temp_files.append(output_path)

        # Генерируем голос
        voice_path = tts.text_to_ogg(response, output_path)
        logger.info(f"🔊 Голос сгенерирован: {voice_path}")

        if voice_path and Path(voice_path).exists():
            # Отправляем голосовое сообщение
            logger.info("📤 Отправляю голосовое сообщение...")

            from aiogram.types import FSInputFile
            voice_file = FSInputFile(voice_path)

            await message.answer_voice(
                voice=voice_file,
                caption="_Голосовой ответ сгенерирован_",
                parse_mode="Markdown"
            )
            logger.info("✅ Голосовое сообщение отправлено")

            # Кнопки оценки
            keyboard = InlineKeyboardBuilder()
            keyboard.add(InlineKeyboardButton(text="👍", callback_data=f"like_{message_id}"))
            keyboard.add(InlineKeyboardButton(text="👎", callback_data=f"dislike_{message_id}"))

            await message.answer(
                response + "\n\n_Оцени ответ, пожалуйста:_",
                parse_mode="Markdown",
                reply_markup=keyboard.as_markup()
            )

            # Удаляем статусное сообщение
            await status_msg.delete()
        else:
            logger.error("❌ Не удалось сгенерировать голос")
            await status_msg.edit_text(
                response + "\n\n_(не удалось создать голос, ответ текстом)_",
                parse_mode="Markdown"
            )

    except asyncio.TimeoutError:
        logger.error("❌ Таймаут при скачивании голосового файла")
        await status_msg.edit_text(
            "❌ Превышено время ожидания при скачивании голосового сообщения.\n"
            "Попробуй отправить более короткое сообщение или проверь интернет."
        )
    except Exception as e:
        logger.error(f"❌ Ошибка обработки голоса: {e}", exc_info=True)
        await status_msg.edit_text(
            f"❌ Произошла ошибка при обработке голосового сообщения.\n"
            f"Детали: {str(e)}\n"
            f"Попробуй отправить текст."
        )

    finally:
        # Удаляем временные файлы
        for file_path in temp_files:
            try:
                os.unlink(file_path)
                logger.info(f"🗑️ Удалён временный файл: {file_path}")
            except:
                pass


# ========== ОБРАБОТЧИК ТЕКСТОВЫХ СООБЩЕНИЙ ==========
@dp.message()
async def handle_message(message: types.Message):
    user_id = message.from_user.id

    # Админские состояния
    if is_admin(user_id):
        if 'awaiting_mode_name' in admin_states:
            mode_name = message.text.strip().lower().replace(' ', '_')
            admin_states['new_mode_name'] = mode_name
            admin_states.pop('awaiting_mode_name')
            admin_states['awaiting_mode_prompt'] = user_id
            await message.answer(
                f"✅ Название: **{mode_name}**\n\n"
                f"Теперь отправь текст промпта:",
                parse_mode="Markdown"
            )
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

    # Обычный текстовый режим
    mode = db.get_user_mode(user_id)
    system_prompt = db.get_prompt(mode) or "Ты полезный ассистент."
    db.save_message(user_id, 'user', message.text, mode)

    await message.bot.send_chat_action(message.chat.id, action="typing")

    # Получаем ответ от выбранной AI-модели
    user_model = user_models.get(user_id, "gigachat")

    if user_model == "gigachat":
        response = giga.ask(message.text, system_prompt)
    elif user_model == "deepseek":
        response = deepseek.ask(message.text, system_prompt)
    elif user_model in ["mistral", "llama", "qwen", "gemma"]:
        response = openrouter.ask(message.text, model=user_model, system_prompt=system_prompt)
    else:
        response = giga.ask(message.text, system_prompt)

    message_id = db.save_message(user_id, 'assistant', response, mode)

    keyboard = InlineKeyboardBuilder()
    keyboard.add(InlineKeyboardButton(text="👍", callback_data=f"like_{message_id}"))
    keyboard.add(InlineKeyboardButton(text="👎", callback_data=f"dislike_{message_id}"))

    voice_hint = "\n\n_Также ты можешь отправить голосовое сообщение!_" if VOICE_ENABLED else ""

    await message.answer(
        response + voice_hint,
        parse_mode="Markdown",
        reply_markup=keyboard.as_markup()
    )


# ========== ОБРАБОТЧИК ВЕБХУКА ДЛЯ RENDER ==========
async def handle_webhook(request: web.Request) -> web.Response:
    """Обрабатывает входящие обновления от Telegram через вебхук"""
    try:
        update_data = await request.json()
        update = types.Update(**update_data)
        await dp.feed_update(bot, update)
        return web.Response(status=200)
    except Exception as e:
        logger.error(f"❌ Ошибка в вебхуке: {e}", exc_info=True)
        return web.Response(status=500)


async def healthcheck(request: web.Request) -> web.Response:
    """Эндпоинт для проверки здоровья приложения"""
    return web.Response(
        text=f"Bot is running! Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        status=200
    )


async def on_startup():
    """Действия при запуске на Render"""
    if IS_RENDER and PUBLIC_DOMAIN != 'localhost':
        webhook_url = f"https://{PUBLIC_DOMAIN}/webhook"

        # Удаляем старый вебхук и устанавливаем новый
        await bot.delete_webhook(drop_pending_updates=True)
        await bot.set_webhook(
            webhook_url,
            allowed_updates=["message", "callback_query"],
            drop_pending_updates=True
        )
        logger.info(f"✅ Вебхук установлен на {webhook_url}")
    else:
        logger.info("💻 Локальный режим: вебхук не устанавливается")


async def on_shutdown():
    """Действия при остановке"""
    if IS_RENDER:
        await bot.delete_webhook()
    await bot.session.close()
    logger.info("✅ Бот остановлен")


# ========== ЗАПУСК ==========
async def main():
    # Регистрируем функции запуска и остановки
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    if IS_RENDER:
        # Запуск на Render с вебхуками
        app = web.Application()
        app.router.add_post('/webhook', handle_webhook)
        app.router.add_get('/', healthcheck)
        app.router.add_get('/health', healthcheck)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', PORT)
        await site.start()

        logger.info(f"🌐 Веб-сервер запущен на порту {PORT}")
        logger.info(f"🔗 URL вебхука: https://{PUBLIC_DOMAIN}/webhook")
        logger.info("🤖 Бот ожидает обновления через вебхуки...")

        # Бесконечное ожидание
        try:
            await asyncio.Event().wait()
        except KeyboardInterrupt:
            logger.info("🛑 Получен сигнал остановки")
        finally:
            await on_shutdown()
            await runner.cleanup()
    else:
        # Локальный запуск с polling
        logger.info("🚀 Бот запущен в локальном режиме!")
        logger.info(f"🎤 Голосовой режим: {'ВКЛЮЧЕН' if VOICE_ENABLED else 'ВЫКЛЮЧЕН'}")
        await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"💥 Критическая ошибка: {e}", exc_info=True)