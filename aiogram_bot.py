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
import subprocess
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

# ========== УПРОЩЁННЫЙ ГОЛОС (Google Speech + gTTS) ==========
try:
    import speech_recognition as sr
    from gtts import gTTS
    from pydub import AudioSegment


    class SimpleSTT:
        def __init__(self):
            self.recognizer = sr.Recognizer()
            print("✅ Google STT инициализирован")

        def audio_to_text(self, audio_path):
            try:
                with sr.AudioFile(audio_path) as source:
                    audio = self.recognizer.record(source)
                    text = self.recognizer.recognize_google(audio, language="ru-RU")
                    return text
            except sr.UnknownValueError:
                return "🔇 Не удалось распознать речь"
            except sr.RequestError:
                return "❌ Ошибка сервиса распознавания"
            except Exception as e:
                return f"❌ Ошибка: {e}"


    class SimpleTTS:
        def __init__(self):
            self.language = 'ru'
            print("✅ Google TTS инициализирован")

        def set_language(self, lang):
            self.language = lang

        def text_to_ogg(self, text, output_path):
            try:
                # Создаём временный MP3
                mp3_path = output_path.replace('.ogg', '.mp3')
                tts = gTTS(text=text, lang=self.language, slow=False)
                tts.save(mp3_path)

                # Конвертируем в OGG
                audio = AudioSegment.from_mp3(mp3_path)
                audio.export(output_path, format="ogg")

                # Удаляем временный MP3
                os.remove(mp3_path)

                return output_path
            except Exception as e:
                print(f"❌ Ошибка TTS: {e}")
                return None


    # Инициализируем голосовые модули
    stt = SimpleSTT()
    tts = SimpleTTS()
    VOICE_ENABLED = True
    print("🎉 Голосовые модули успешно загружены!")

except ImportError as e:
    print(f"⚠️ Библиотеки не установлены: {e}")
    print("💡 Установите: pip install SpeechRecognition gtts pydub")
    VOICE_ENABLED = False
    stt = None
    tts = None
except Exception as e:
    print(f"❌ Ошибка инициализации голоса: {e}")
    VOICE_ENABLED = False
    stt = None
    tts = None

# ========== ОПРЕДЕЛЕНИЕ СРЕДЫ ==========
IS_RENDER = os.environ.get('RENDER') is not None

if IS_RENDER:
    PORT = int(os.environ.get('PORT', 10000))
    RENDER_EXTERNAL_URL = os.environ.get('RENDER_EXTERNAL_URL')
    if RENDER_EXTERNAL_URL:
        PUBLIC_DOMAIN = RENDER_EXTERNAL_URL.replace('https://', '')
    else:
        PUBLIC_DOMAIN = 'localhost'
    print(f"🚀 Запуск на Render: {PUBLIC_DOMAIN}")
    USE_WEBHOOK = True
else:
    PORT = 8080
    PUBLIC_DOMAIN = 'localhost'
    print("💻 Локальный запуск")
    USE_WEBHOOK = False

# ========== НАСТРОЙКИ ==========
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
if not TELEGRAM_TOKEN:
    TELEGRAM_TOKEN = "8249255843:AAE0fPLcPpmJqyWGK70xJ06mOacatNVEUgc"
    print("⚠️ Токен взят из кода")

CLIENT_ID = os.environ.get('CLIENT_ID', "019c9dd5-08ad-714c-8358-5945e8c15fee")
CLIENT_SECRET = os.environ.get('CLIENT_SECRET', "90a0e997-4015-458f-907a-d59f5d9e68a7")
ADMIN_IDS = [1467484237, 8249255843]

print(f"🔑 Токен: {TELEGRAM_TOKEN[:10]}...")
print(f"🔑 Client ID: {CLIENT_ID[:10]}...")

# ========== ИНИЦИАЛИЗАЦИЯ ==========
admin_states = {}
db = Database()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

session = AiohttpSession(
    api=TelegramAPIServer.from_base('https://api.telegram.org'),
    timeout=300
)

bot = Bot(
    token=TELEGRAM_TOKEN,
    session=session,
    default=DefaultBotProperties(parse_mode="HTML")
)
dp = Dispatcher()

# ========== AI-МОДЕЛИ ==========
giga = GigaChatModel(CLIENT_ID, CLIENT_SECRET)
deepseek = DeepSeekModel()
openrouter = OpenRouterModel()

user_models = {}

model_names = {
    "gigachat": "🇷🇺 GigaChat",
    "deepseek": "🇨🇳 DeepSeek",
    "mistral": "🇪🇺 Mistral",
    "llama": "🦙 Llama",
    "qwen": "🇨🇳 Qwen",
    "gemma": "🇺🇸 Gemma"
}

model_descriptions = {
    "gigachat": "🇷🇺 <b>GigaChat</b>\n• От Сбера\n• Лучший русский язык\n• Бесплатно",
    "deepseek": "🇨🇳 <b>DeepSeek</b>\n• 1 млн токенов\n• Очень быстрый\n• Отличный код",
    "mistral": "🇪🇺 <b>Mistral</b>\n• Европейская модель\n• Открытый код\n• Хороша для логики",
    "llama": "🦙 <b>Llama</b>\n• От Meta\n• Самая популярная\n• 8B параметров",
    "qwen": "🇨🇳 <b>Qwen</b>\n• От Alibaba\n• 7B параметров\n• Сильная в математике",
    "gemma": "🇺🇸 <b>Gemma</b>\n• От Google\n• 9B параметров\n• Новая технология"
}

FACTS = [
    "🧠 Python назван в честь Monty Python",
    "📱 Первое SMS: Merry Christmas",
    "💻 Первый вирус: Elk Cloner",
    "🔍 Google назывался Backrub",
    "🎮 Minecraft - самая продаваемая",
    "🌐 Первый сайт: info.cern.ch",
]


def is_admin(user_id):
    return str(user_id) in [str(admin_id) for admin_id in ADMIN_IDS]


# ========== ОБРАБОТЧИКИ ==========

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

    voice_status = "🎤 Голос активен (Google)" if VOICE_ENABLED else "⚠️ Голос отключен"

    await message.answer(
        f"👋 <b>Привет, {first_name}!</b>\n\n"
        f"🧠 <b>Нейробот Вики</b>\n"
        f"🤖 <b>Модель:</b> {model_display}\n"
        f"{voice_status}\n\n"
        f"👇 <b>Выбери режим:</b>",
        parse_mode="HTML",
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

    text = f"🤖 <b>Выбери AI-модель:</b>\n\n"
    text += f"🔹 <b>Сейчас выбрана:</b> {current_display}\n\n"
    text += "<b>Что умеют модели:</b>\n\n"

    for model_key, desc in model_descriptions.items():
        if model_key == current_model:
            text += f"⭐ {desc} (текущая)\n\n"
        else:
            text += f"• {desc}\n\n"

    await message.answer(text, parse_mode="HTML", reply_markup=keyboard.as_markup())


@dp.message(Command("help"))
async def help_command(message: types.Message):
    await message.answer(
        "🤖 <b>Доступные команды:</b>\n\n"
        "📌 <b>Основные:</b>\n"
        "/start - Главное меню\n"
        "/help - Эта справка\n"
        "/stats - Статистика\n"
        "/clear - Сбросить диалог\n\n"
        "📝 <b>Заметки:</b>\n"
        "/note текст - сохранить\n"
        "/notes - показать\n"
        "/delnote номер - удалить\n\n"
        "🤖 <b>AI-модели:</b>\n"
        "/model - Выбрать модель\n\n"
        "🔧 <b>Полезные:</b>\n"
        "/time - Время\n"
        "/random - Случайное число\n"
        "/fact - Интересный факт\n\n"
        "🎤 <b>Голос (Google):</b>\n"
        "/voice_ru - Русский\n"
        "/voice_en - Английский\n"
        "Отправь голосовое!",
        parse_mode="HTML"
    )


@dp.message(Command("time"))
async def time_command(message: types.Message):
    now = datetime.now()
    await message.answer(
        f"📅 <b>Сегодня:</b> {now.strftime('%d.%m.%Y')}\n"
        f"⏰ <b>Время:</b> {now.strftime('%H:%M:%S')}",
        parse_mode="HTML"
    )


@dp.message(Command("random"))
async def random_command(message: types.Message):
    args = message.text.split()
    if len(args) == 3:
        try:
            min_num = int(args[1])
            max_num = int(args[2])
            number = random.randint(min_num, max_num)
            await message.answer(f"🎲 <b>Число от {min_num} до {max_num}:</b> {number}", parse_mode="HTML")
        except:
            await message.answer("❌ Используй: /random мин макс", parse_mode="HTML")
    else:
        number = random.randint(1, 100)
        await message.answer(f"🎲 <b>Случайное число:</b> {number}", parse_mode="HTML")


@dp.message(Command("fact"))
async def fact_command(message: types.Message):
    fact = random.choice(FACTS)
    await message.answer(f"🔮 <b>Факт:</b>\n\n{fact}", parse_mode="HTML")


@dp.message(Command("stats"))
async def stats_command(message: types.Message):
    stats = db.get_user_stats(message.from_user.id)
    await message.answer(
        f"📊 <b>Твоя статистика:</b>\n\n"
        f"• Сообщений: {stats['messages']}\n"
        f"• 👍 Лайков: {stats['likes']}\n"
        f"• 👎 Дизлайков: {stats['dislikes']}",
        parse_mode="HTML"
    )


@dp.message(Command("clear"))
async def clear_command(message: types.Message):
    await message.answer("✅ Диалог сброшен. /start", parse_mode="HTML")


@dp.message(Command("voice_ru"))
async def voice_ru(message: types.Message):
    if VOICE_ENABLED and tts:
        tts.set_language('ru')
        await message.answer("✅ Голос переключён на <b>русский</b> (Google)", parse_mode="HTML")
    else:
        await message.answer("❌ Голос недоступен", parse_mode="HTML")


@dp.message(Command("voice_en"))
async def voice_en(message: types.Message):
    if VOICE_ENABLED and tts:
        tts.set_language('en')
        await message.answer("✅ Голос переключён на <b>английский</b> (Google)", parse_mode="HTML")
    else:
        await message.answer("❌ Голос недоступен", parse_mode="HTML")


@dp.message(Command("cancel"))
async def cancel_command(message: types.Message):
    user_id = message.from_user.id
    cancelled = False
    for key in list(admin_states.keys()):
        if admin_states[key] == user_id:
            del admin_states[key]
            cancelled = True
    if cancelled:
        await message.answer("✅ Действие отменено", parse_mode="HTML")
    else:
        await message.answer("❌ Нет активных действий", parse_mode="HTML")


# ========== ЗАМЕТКИ ==========

@dp.message(Command("note"))
async def note_command(message: types.Message):
    text = message.text.replace("/note", "", 1).strip()
    if not text:
        await message.answer(
            "📝 <b>Как пользоваться:</b>\n\n"
            "/note текст - сохранить\n"
            "/notes - показать\n"
            "/delnote номер - удалить",
            parse_mode="HTML"
        )
        return
    user_id = message.from_user.id
    note_id = db.save_note(user_id, text)
    await message.answer(
        f"✅ <b>Заметка сохранена!</b>\n\n📝 {text}\n\n📌 Номер: {note_id}",
        parse_mode="HTML"
    )


@dp.message(Command("notes"))
async def notes_command(message: types.Message):
    user_id = message.from_user.id
    notes = db.get_notes(user_id)
    if not notes:
        await message.answer("📭 <b>Нет заметок</b>\n\n/note текст - создать", parse_mode="HTML")
        return
    text = "📝 <b>Твои заметки:</b>\n\n"
    for note in notes[:10]:
        created = note['created_at'][:16] if note['created_at'] else ""
        text += f"📌 <code>{note['note']}</code>\n   🆔 {note['id']} | {created}\n\n"
    await message.answer(text, parse_mode="HTML")


@dp.message(Command("delnote"))
async def delnote_command(message: types.Message):
    args = message.text.split()
    if len(args) < 2:
        await message.answer("❌ <b>Укажи номер</b>\n\n/delnote 5", parse_mode="HTML")
        return
    try:
        note_id = int(args[1])
        user_id = message.from_user.id
        if db.delete_note(note_id, user_id):
            await message.answer(f"✅ <b>Заметка {note_id} удалена</b>", parse_mode="HTML")
        else:
            await message.answer(f"❌ <b>Заметка {note_id} не найдена</b>", parse_mode="HTML")
    except ValueError:
        await message.answer("❌ <b>Номер должен быть числом</b>", parse_mode="HTML")


@dp.callback_query(lambda c: c.data == "notes_menu")
async def notes_menu_callback(callback: types.CallbackQuery):
    keyboard = InlineKeyboardBuilder()
    keyboard.add(InlineKeyboardButton(text="📝 Показать", callback_data="notes_show"))
    keyboard.add(InlineKeyboardButton(text="➕ Добавить", callback_data="notes_add"))
    keyboard.add(InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main"))
    keyboard.adjust(1)
    await callback.message.edit_text(
        "📝 <b>Записной блокнот</b>",
        parse_mode="HTML",
        reply_markup=keyboard.as_markup()
    )


@dp.callback_query(lambda c: c.data == "notes_show")
async def notes_show_callback(callback: types.CallbackQuery):
    await callback.answer()
    await notes_command(callback.message)


@dp.callback_query(lambda c: c.data == "notes_add")
async def notes_add_callback(callback: types.CallbackQuery):
    await callback.answer()
    await callback.message.answer("📝 <b>Напиши текст заметки</b>\n/note текст", parse_mode="HTML")


# ========== ГОЛОСОВЫЕ СООБЩЕНИЯ ==========
@dp.message(lambda message: message.voice is not None)
async def voice_message_handler(message: types.Message):
    if not VOICE_ENABLED or not stt or not tts:
        await message.answer("❌ Голос временно недоступен. Отправь текст.")
        return

    user_id = message.from_user.id
    logger.info(f"🎤 Голосовое от {user_id}")

    mode = db.get_user_mode(user_id)
    system_prompt = db.get_prompt(mode) or "Ты полезный ассистент."

    status_msg = await message.answer("🎤 Распознаю речь через Google...")
    temp_files = []

    try:
        # Скачиваем голосовое
        file = await message.bot.get_file(message.voice.file_id)
        with tempfile.NamedTemporaryFile(suffix='.ogg', delete=False) as tmp_file:
            await message.bot.download_file(file.file_path, tmp_file.name)
            ogg_path = tmp_file.name
            temp_files.append(ogg_path)

        # Распознаём речь
        await status_msg.edit_text("🔄 Распознавание...")
        recognized_text = stt.audio_to_text(ogg_path)

        if recognized_text.startswith("❌") or recognized_text.startswith("🔇"):
            await status_msg.edit_text(recognized_text)
            return

        await status_msg.edit_text(f"📝 <b>Распознано:</b> {recognized_text}\n\n🤔 Думаю...", parse_mode="HTML")
        db.save_message(user_id, 'user', f"[голос] {recognized_text}", mode)

        # Ответ AI
        user_model = user_models.get(user_id, "gigachat")
        if user_model == "gigachat":
            response = giga.ask(recognized_text, system_prompt)
        elif user_model == "deepseek":
            response = deepseek.ask(recognized_text, system_prompt)
        else:
            response = openrouter.ask(recognized_text, model=user_model, system_prompt=system_prompt)

        message_id = db.save_message(user_id, 'assistant', response, mode)

        # Создаём голосовой ответ через Google TTS
        await status_msg.edit_text("🔊 Создаю голос через Google...")

        with tempfile.NamedTemporaryFile(suffix='.ogg', delete=False) as tmp_file:
            output_path = tmp_file.name
            temp_files.append(output_path)

        voice_path = tts.text_to_ogg(response, output_path)

        if voice_path and Path(voice_path).exists():
            from aiogram.types import FSInputFile
            voice_file = FSInputFile(voice_path)

            await message.answer_voice(
                voice=voice_file,
                caption="<i>Google TTS</i>",
                parse_mode="HTML"
            )

            keyboard = InlineKeyboardBuilder()
            keyboard.add(InlineKeyboardButton(text="👍", callback_data=f"like_{message_id}"))
            keyboard.add(InlineKeyboardButton(text="👎", callback_data=f"dislike_{message_id}"))

            await message.answer(
                response + "\n\n<i>Оцени ответ:</i>",
                parse_mode="HTML",
                reply_markup=keyboard.as_markup()
            )
            await status_msg.delete()
        else:
            await status_msg.edit_text(response + "\n\n(голос не создан)", parse_mode="HTML")

    except Exception as e:
        logger.error(f"❌ Ошибка голоса: {e}")
        await status_msg.edit_text("❌ Ошибка обработки голоса")
    finally:
        for f in temp_files:
            try:
                os.unlink(f)
            except:
                pass


# ========== КНОПКИ ==========
@dp.callback_query()
async def callback_handler(callback: types.CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id
    username = callback.from_user.username
    first_name = callback.from_user.first_name
    last_name = callback.from_user.last_name

    if callback.data.startswith(('like_', 'dislike_')):
        parts = callback.data.split('_')
        rating = 1 if parts[0] == 'like' else -1
        message_id = int(parts[1])
        db.save_feedback(user_id, message_id, rating)
        await callback.message.edit_text(
            callback.message.text.replace("\n\n<i>Оцени ответ:</i>", ""),
            parse_mode="HTML"
        )
        return

    if callback.data == "back_to_main":
        await start(callback.message)
        return

    if callback.data == "notes_menu":
        await notes_menu_callback(callback)
        return

    if callback.data == "model_menu":
        await model_command(callback.message)
        return

    if callback.data.startswith("model_"):
        model = callback.data.replace("model_", "")
        user_models[user_id] = model
        await callback.message.answer(
            f"✅ <b>Модель: {model_names.get(model, model)}</b>",
            parse_mode="HTML"
        )
        return

    if callback.data.startswith("mode_"):
        mode = callback.data.replace("mode_", "")
        db.set_user_mode(user_id, mode, username, first_name, last_name)
        await callback.message.answer(
            f"✅ <b>Режим «{mode}» активирован!</b>",
            parse_mode="HTML"
        )
        return

    if callback.data == "help":
        await help_command(callback.message)
        return

    if callback.data == "stats":
        stats = db.get_user_stats(user_id)
        await callback.message.answer(
            f"📊 <b>Статистика:</b>\n\n"
            f"• Сообщений: {stats['messages']}\n"
            f"• 👍: {stats['likes']}\n"
            f"• 👎: {stats['dislikes']}",
            parse_mode="HTML"
        )
        return

    if is_admin(user_id) and callback.data == "admin_menu":
        prompts = db.get_all_prompts()
        text = "📋 <b>Промпты:</b>\n\n"
        for mode, prompt in prompts.items():
            short = prompt[:50] + "..." if len(prompt) > 50 else prompt
            text += f"• <b>{mode}</b>: {short}\n\n"
        await callback.message.answer(text, parse_mode="HTML")
        return


# ========== ТЕКСТОВЫЕ СООБЩЕНИЯ ==========
@dp.message()
async def handle_message(message: types.Message):
    user_id = message.from_user.id

    if is_admin(user_id):
        if 'awaiting_mode_name' in admin_states:
            mode_name = message.text.strip().lower().replace(' ', '_')
            admin_states['new_mode_name'] = mode_name
            admin_states.pop('awaiting_mode_name')
            admin_states['awaiting_mode_prompt'] = user_id
            await message.answer(f"✅ <b>{mode_name}</b>\n\nТеперь отправь промпт:", parse_mode="HTML")
            return

        if 'awaiting_mode_prompt' in admin_states:
            mode_name = admin_states.get('new_mode_name')
            if db.add_prompt(mode_name, message.text):
                await message.answer(f"✅ Режим <b>{mode_name}</b> создан!", parse_mode="HTML")
            else:
                await message.answer("❌ Ошибка: режим существует", parse_mode="HTML")
            admin_states.pop('awaiting_mode_prompt', None)
            admin_states.pop('new_mode_name', None)
            return

        for mode, admin_id in list(admin_states.items()):
            if admin_id == user_id and mode not in ['awaiting_mode_name', 'awaiting_mode_prompt']:
                if db.update_prompt(mode, message.text):
                    await message.answer(f"✅ Промпт <b>{mode}</b> обновлён!", parse_mode="HTML")
                else:
                    await message.answer("❌ Ошибка", parse_mode="HTML")
                admin_states.pop(mode)
                return

    mode = db.get_user_mode(user_id)
    system_prompt = db.get_prompt(mode) or "Ты полезный ассистент."
    db.save_message(user_id, 'user', message.text, mode)

    await message.bot.send_chat_action(message.chat.id, action="typing")
    user_model = user_models.get(user_id, "gigachat")

    try:
        if user_model == "gigachat":
            response = giga.ask(message.text, system_prompt)
        elif user_model == "deepseek":
            response = deepseek.ask(message.text, system_prompt)
        else:
            response = openrouter.ask(message.text, model=user_model, system_prompt=system_prompt)
    except Exception as e:
        response = f"❌ Ошибка AI: {str(e)}"

    message_id = db.save_message(user_id, 'assistant', response, mode)

    keyboard = InlineKeyboardBuilder()
    keyboard.add(InlineKeyboardButton(text="👍", callback_data=f"like_{message_id}"))
    keyboard.add(InlineKeyboardButton(text="👎", callback_data=f"dislike_{message_id}"))

    hint = "\n\n<i>Отправь голосовое!</i>" if VOICE_ENABLED else ""
    await message.answer(response + hint, parse_mode="HTML", reply_markup=keyboard.as_markup())


# ========== ВЕБХУК ==========
async def handle_webhook(request: web.Request) -> web.Response:
    try:
        update_data = await request.json()
        update = types.Update(**update_data)
        await dp.feed_update(bot, update)
        return web.Response(status=200)
    except Exception as e:
        logger.error(f"❌ Вебхук: {e}")
        return web.Response(status=500)


async def healthcheck(request: web.Request) -> web.Response:
    return web.Response(text=f"Бот работает! Голос: {'✅' if VOICE_ENABLED else '❌'}")


async def on_startup():
    if USE_WEBHOOK:
        await bot.delete_webhook(drop_pending_updates=True)
        webhook_url = f"https://{PUBLIC_DOMAIN}/webhook"
        await bot.set_webhook(webhook_url, allowed_updates=["message", "callback_query"])
        logger.info(f"✅ Вебхук: {webhook_url}")


async def on_shutdown():
    if USE_WEBHOOK:
        await bot.delete_webhook()
    await bot.session.close()


async def main():
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    if USE_WEBHOOK:
        app = web.Application()
        app.router.add_post('/webhook', handle_webhook)
        app.router.add_get('/', healthcheck)
        app.router.add_get('/health', healthcheck)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', PORT)
        await site.start()

        logger.info(f"🌐 Веб-сервер: {PORT}")
        logger.info(f"🔗 {PUBLIC_DOMAIN}/webhook")
        logger.info(f"🎤 Голос: {'ВКЛ' if VOICE_ENABLED else 'ВЫКЛ'}")

        await asyncio.Event().wait()
    else:
        await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())