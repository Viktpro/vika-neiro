from aiohttp import web
import asyncio
import threading


async def healthcheck(request):
    """Простая проверка, что сервер жив"""
    return web.Response(text="Bot is running!")


async def run_web_server():
    """Запуск веб-сервера на порту 8080"""
    app = web.Application()
    app.router.add_get('/', healthcheck)
    app.router.add_get('/health', healthcheck)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8080)
    await site.start()
    print("✅ Веб-сервер для healthcheck запущен на порту 8080")

    # Держим сервер запущенным
    await asyncio.Event().wait()


def start_web_server():
    """Запуск веб-сервера в отдельном потоке"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(run_web_server())
    except KeyboardInterrupt:
        pass
    finally:
        loop.close()


def start_web_server_thread():
    """Запускает веб-сервер в отдельном потоке"""
    thread = threading.Thread(target=start_web_server, daemon=True)
    thread.start()
    return thread