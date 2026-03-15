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
from aiohttp import web
from database import Database
from ai_models import DeepSeekModel, OpenRouterModel, GigaChatModel

# ========== ОПРЕДЕЛЕНИЕ СРЕДЫ ==========
# Определяем, на Render ли мы
IS_RENDER = os.environ.get('RENDER') is not None

if IS_RENDER:
    # На Render используем webhook
    PORT = int(os.environ.get('PORT', 10000))
    RENDER_EXTERNAL_URL = os.environ.get('RENDER_EXTERNAL_URL')
    if RENDER_EXTERNAL_URL:
        PUBLIC_DOMAIN = RENDER_EXTERNAL_URL.replace('https://', '')
    else:
        PUBLIC_DOMAIN = 'localhost'
    print(f"🚀 Запуск на Render: {PUBLIC_DOMAIN}")
    USE_WEBHOOK = True
else:
    # Локально используем polling
    PORT = 8080
    PUBLIC_DOMAIN = 'localhost'
    print("💻 Локальный запуск")
    USE_WEBHOOK = False

# ========== НАСТРОЙКИ ==========
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
if not TELEGRAM_TOKEN:
    TELEGRAM_TOKEN = "8249255843:AAE0fPLcPpmJqyWGK70xJ06mOacatNVEUgc"
    print("⚠️ Токен взят из кода (не из переменных окружения)")

CLIENT_ID = os.environ.get('CLIENT_ID', "019c9dd5-08ad-714c-8358-5945e8c15fee")
CLIENT_SECRET = os.environ.get('CLIENT_SECRET', "90a0e997-4015-458f-907a-d59f5d9e68a7")
ADMIN_IDS = [1467484237, 8249255843]

print(f"🔑 Токен загружен: {TELEGRAM_TOKEN[:10]}...")
print(f"🔑 Client ID: {CLIENT_ID[:10]}...")

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

# ========== ГОЛОСОВЫЕ МОДУЛИ ==========
try:
    from voice.stt import STT
    from voice.tts import TTS

    VOICE_ENABLED = True
    try:
        stt = STT()
        tts = TTS()
        print("✅ Голосовые модули инициализированы")
    except Exception as e:
        print(f"❌ Ошибка инициализации голоса: {e}")
        VOICE_ENABLED = False
except ImportError as e:
    print(f"⚠️ Голосовые модули не загружены: {e}")
    VOICE_ENABLED = False

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
    "llama": "🦙 **Llama**\n• От Meta\n• Самая популярная\n• 8B параметров",
    "qwen": "🇨🇳 **Qwen**\n• От Alibaba\n• 7B параметров\n• Сильная в математике",
    "gemma": "🇺🇸 **Gemma**\n• От Google\n• 9B параметров\n• Новая технология"
}

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
    voice_status = "🎤 Голос активен" if VOICE_ENABLED else "⚠️ Голос отключен"

    await message.answer(
        f"👋 **Привет, {first_name}!**\n\n"
        f"🧠 **Нейробот Вики**\n"
        f"🤖 **Модель:** {model_display}\n"
        f"{voice_status}\n\n"
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
        "/fact - Интересный факт\n\n"
        "🎤 **Голос:**\n"
        "/voice_ru - Русский голос\n"
        "/voice_en - Английский голос\n"
        "Или просто отправь голосовое сообщение!",
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


@dp.message(Command("voice_ru"))
async def voice_ru(message: types.Message):
    if VOICE_ENABLED:
        tts.set_language('ru')
        await message.answer("✅ Голос переключён на **русский**", parse_mode="Markdown")
    else:
        await message.answer("❌ Голосовой режим недоступен")


@dp.message(Command("voice_en"))
async def voice_en(message: types.Message):
    if VOICE_ENABLED:
        tts.set_language('en')
        await message.answer("✅ Голос переключён на **английский**", parse_mode="Markdown")
    else:
        await message.answer("❌ Голосовой режим недоступен")


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
        created = note['created_at'][:16] if note['created_at'] else ""
        text += f"📌 `{note['note']}`\n"
        text += f"   🆔 {note['id']} | {created}\n\n"

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


# ========== ОБРАБОТЧИК ГОЛОСОВЫХ СООБЩЕНИЙ ==========
@dp.message(lambda message: message.voice is not None)
async def voice_message_handler(message: types.Message):
    """Обработчик голосовых сообщений"""

    if not VOICE_ENABLED:
        await message.answer("❌ Голосовой режим временно недоступен. Отправь текст.")
        return

    user_id = message.from_user.id
    logger.info(f"🎤 Получено голосовое сообщение от пользователя {user_id}")

    mode = db.get_user_mode(user_id)
    system_prompt = db.get_prompt(mode) or "Ты полезный ассистент."

    status_msg = await message.answer("🎤 Распознаю речь...")

    temp_files = []

    try:
        # Скачиваем голосовое сообщение
        logger.info("📥 Скачиваю голосовой файл...")
        file = await message.bot.get_file(message.voice.file_id)

        with tempfile.NamedTemporaryFile(suffix='.ogg', delete=False) as tmp_file:
            await message.bot.download_file(file.file_path, tmp_file.name)
            ogg_path = tmp_file.name
            temp_files.append(ogg_path)
            logger.info(f"✅ Файл скачан: {ogg_path}")

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

        db.save_message(user_id, 'user', f"[голосовое] {recognized_text}", mode)

        # Получаем ответ от AI
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

        message_id = db.save_message(user_id, 'assistant', response, mode)

        # Создаём голосовой ответ
        await status_msg.edit_text("🔊 Создаю голосовой ответ...")
        logger.info("🔊 Генерирую голос через TTS...")

        with tempfile.NamedTemporaryFile(suffix='.ogg', delete=False) as tmp_file:
            output_path = tmp_file.name
            temp_files.append(output_path)

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

            await status_msg.delete()
        else:
            logger.error("❌ Не удалось сгенерировать голос")
            await status_msg.edit_text(
                response + "\n\n_(не удалось создать голос, ответ текстом)_",
                parse_mode="Markdown"
            )

    except Exception as e:
        logger.error(f"❌ Ошибка обработки голоса: {e}", exc_info=True)
        await status_msg.edit_text(
            f"❌ Произошла ошибка при обработке голосового сообщения.\n"
            f"Попробуй отправить текст."
        )

    finally:
        for file_path in temp_files:
            try:
                os.unlink(file_path)
            except:
                pass


# ========== ОБРАБОТЧИК КНОПОК ==========

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

    # Админ-меню
    if is_admin(user_id):
        if callback.data == "admin_menu":
            prompts = db.get_all_prompts()
            text = "📋 **Системные промпты:**\n\n"
            for mode, prompt in prompts.items():
                short_prompt = prompt[:50] + "..." if len(prompt) > 50 else prompt
                text += f"• **{mode}**: {short_prompt}\n\n"
            await callback.message.answer(text, parse_mode="Markdown")
            return


# ========== ОСНОВНОЙ ОБРАБОТЧИК ТЕКСТА ==========

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

    # Обычный текстовый режим
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
    """Действия при запуске"""
    if USE_WEBHOOK:
        # Удаляем старый вебхук и устанавливаем новый
        await bot.delete_webhook(drop_pending_updates=True)
        webhook_url = f"https://{PUBLIC_DOMAIN}/webhook"
        await bot.set_webhook(
            webhook_url,
            allowed_updates=["message", "callback_query"],
            drop_pending_updates=True
        )
        logger.info(f"✅ Вебхук установлен на {webhook_url}")

        # Проверяем вебхук
        webhook_info = await bot.get_webhook_info()
        logger.info(f"📊 Информация о вебхуке: {webhook_info.url}")
    else:
        logger.info("💻 Локальный режим: используем polling")

    bot_info = await bot.get_me()
    logger.info(f"🚀 Бот @{bot_info.username} запущен!")
    logger.info(f"🎤 Голосовой режим: {'ВКЛЮЧЕН' if VOICE_ENABLED else 'ВЫКЛЮЧЕН'}")


async def on_shutdown():
    """Действия при остановке"""
    if USE_WEBHOOK:
        await bot.delete_webhook()
    await bot.session.close()
    logger.info("✅ Бот остановлен, вебхук удалён")


# ========== ОСНОВНАЯ ФУНКЦИЯ ==========
async def main():
    # Регистрируем функции запуска и остановки
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    if USE_WEBHOOK:
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


# ========== ЗАПУСК ==========
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"💥 Критическая ошибка: {e}", exc_info=True)