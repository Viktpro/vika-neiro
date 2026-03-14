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
from aiohttp import web  # Важно: импортируем aiohttp
from database import Database
from ai_models import DeepSeekModel, OpenRouterModel, GigaChatModel

# ========== НАСТРОЙКИ ==========
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
if not TELEGRAM_TOKEN:
    TELEGRAM_TOKEN = "8249255843:AAE0fPLcPpmJqyWGK70xJ06mOacatNVEUgc"
    print("⚠️ Токен взят из кода (не из переменных окружения)")

CLIENT_ID = os.environ.get('CLIENT_ID', "019c9dd5-08ad-714c-8358-5945e8c15fee")
CLIENT_SECRET = os.environ.get('CLIENT_SECRET', "90a0e997-4015-458f-907a-d59f5d9e68a7")
ADMIN_IDS = [1467484237, 8249255843]  # Оба твоих ID

# Для Railway важно получить порт из переменных окружения
PORT = int(os.environ.get('PORT', 8080))
# Домен приложения для вебхука
RAILWAY_PUBLIC_DOMAIN = os.environ.get('RAILWAY_PUBLIC_DOMAIN', 'localhost')

print(f"🔑 Токен загружен: {TELEGRAM_TOKEN[:10]}...")
print(f"🔑 Client ID: {CLIENT_ID[:10]}...")
print(f"🌐 Публичный домен: {RAILWAY_PUBLIC_DOMAIN}")
print(f"🚪 Порт: {PORT}")

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
    "llama": "🦙 **Llama**\n• От Meta (Facebook)\n• Самая популярная\n• 8B параметров",
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


# ========== ЗДЕСЬ ВСЕ ВАШИ ОБРАБОТЧИКИ КОМАНД И КНОПОК ==========
# @dp.message(Command("start"))
# @dp.message(Command("model"))
# @dp.callback_query()
# и так далее...
# Вставьте сюда ВСЕ ваши существующие обработчики из оригинального файла
# (весь код от @dp.message(Command("start")) до @dp.message())

# ========== ОБРАБОТЧИК ВЕБХУКА ==========
async def handle_webhook(request: web.Request) -> web.Response:
    """Обрабатывает входящие обновления от Telegram."""
    try:
        update_data = await request.json()
        update = types.Update(**update_data)
        await dp.feed_update(bot, update)
        return web.Response(status=200)
    except Exception as e:
        logger.error(f"❌ Ошибка в вебхуке: {e}", exc_info=True)
        return web.Response(status=500)


# ========== HEALTHCHECK ДЛЯ RAILWAY ==========
async def healthcheck(request: web.Request) -> web.Response:
    """Эндпоинт для проверки здоровья приложения."""
    return web.Response(
        text=f"Bot is running! Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        status=200
    )


# ========== ФУНКЦИИ ЗАПУСКА И ОСТАНОВКИ ==========
async def on_startup():
    """Действия при запуске бота."""
    # Формируем URL вебхука
    webhook_url = f"https://{RAILWAY_PUBLIC_DOMAIN}/webhook"

    # Удаляем старый вебхук и устанавливаем новый
    await bot.delete_webhook(drop_pending_updates=True)
    await bot.set_webhook(
        webhook_url,
        allowed_updates=dp.resolve_used_update_types(),
        drop_pending_updates=True
    )
    logger.info(f"✅ Вебхук установлен на {webhook_url}")

    # Выводим информацию о боте
    bot_info = await bot.get_me()
    logger.info(f"🚀 Бот @{bot_info.username} запущен!")
    logger.info(f"🎤 Голосовой режим: {'ВКЛЮЧЕН' if VOICE_ENABLED else 'ВЫКЛЮЧЕН'}")


async def on_shutdown():
    """Действия при остановке бота."""
    # Удаляем вебхук
    await bot.delete_webhook()
    # Закрываем сессию
    await bot.session.close()
    logger.info("✅ Бот остановлен, вебхук удалён")


# ========== ОСНОВНАЯ ФУНКЦИЯ ==========
async def main():
    # Регистрируем функции запуска и остановки
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    # Создаём aiohttp приложение
    app = web.Application()
    app.router.add_post('/webhook', handle_webhook)
    app.router.add_get('/', healthcheck)
    app.router.add_get('/health', healthcheck)

    # Запускаем веб-сервер
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()

    logger.info(f"🌐 Веб-сервер запущен на порту {PORT}")
    logger.info("🤖 Бот ожидает обновления через вебхуки...")

    # Бесконечное ожидание (держим процесс запущенным)
    try:
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        logger.info("🛑 Получен сигнал остановки")
    finally:
        await on_shutdown()
        await runner.cleanup()


# ========== ЗАПУСК ==========
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"💥 Критическая ошибка: {e}", exc_info=True)