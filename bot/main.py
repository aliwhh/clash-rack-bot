"""Application Entry Point and Lifecycle Manager (Dual-Mode: Webhook for PaaS / Polling for Local)."""

import asyncio
import logging
import os
import sys
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

from bot.config import settings
from bot.database.session import close_db, init_db
from bot.handlers import main_router
from bot.middlewares import (
    AuthMiddleware,
    ChannelJoinMiddleware,
    DbSessionMiddleware,
    MaintenanceMiddleware,
)
from bot.scheduler import setup_scheduler

# Configure logging
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/bot.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("clash_rack_bot")


async def set_bot_commands(bot: Bot) -> None:
    """Register menu commands with Telegram API."""
    commands = [
        BotCommand(command="start", description="⚡️ شروع و منوی اصلی ربات"),
        BotCommand(command="admin", description="⚙️ پنل مدیریت (مخصوص ادمین)"),
    ]
    try:
        await bot.set_my_commands(commands)
    except Exception as exc:
        logger.warning("Failed to set bot commands: %s", exc)


async def run_webhook(
    bot: Bot,
    dp: Dispatcher,
    scheduler,
    webhook_url: str,
    port: int
) -> None:
    """Run bot in webhook mode for cloud platforms (Render, Koyeb, Railway)."""
    app = web.Application()

    async def health(request: web.Request) -> web.Response:
        return web.Response(text="OK - Clash Rack Rental Bot is running!", status=200)

    app.router.add_get("/", health)
    app.router.add_get("/health", health)

    async def on_startup(app: web.Application) -> None:
        full_url = f"{webhook_url.rstrip('/')}/webhook"
        logger.info("Setting Telegram Webhook to: %s", full_url)
        await bot.set_webhook(
            url=full_url,
            drop_pending_updates=True,
            allowed_updates=dp.resolve_used_update_types(),
        )
        scheduler.start()
        logger.info("Background APScheduler started.")

    async def on_shutdown(app: web.Application) -> None:
        logger.info("Shutting down webhook services...")
        scheduler.shutdown(wait=False)
        await close_db()
        await bot.session.close()
        logger.info("Webhook shutdown completed cleanly.")

    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)

    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path="/webhook")
    setup_application(app, dp, bot=bot)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info("Webhook web server listening on 0.0.0.0:%d (endpoint: %s/webhook)", port, webhook_url)

    try:
        # Keep running until process interrupted
        await asyncio.Event().wait()
    except (asyncio.CancelledError, KeyboardInterrupt):
        pass
    finally:
        await runner.cleanup()


async def run_polling(
    bot: Bot,
    dp: Dispatcher,
    scheduler,
    port: int = None
) -> None:
    """Run bot in long-polling mode (for local development or VPS)."""
    web_runner = None
    if port:
        app = web.Application()
        async def health(req):
            return web.Response(text="OK - Clash Rack Rental Bot is running!", status=200)
        app.router.add_get("/", health)
        app.router.add_get("/health", health)
        web_runner = web.AppRunner(app)
        await web_runner.setup()
        site = web.TCPSite(web_runner, "0.0.0.0", port)
        await site.start()
        logger.info("Local healthcheck server listening on 0.0.0.0:%d", port)

    scheduler.start()
    logger.info("Background APScheduler started.")
    logger.info("Bot is now listening for Telegram updates via long polling...")

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    except Exception as exc:
        logger.error("Error during polling: %s", exc, exc_info=True)
    finally:
        logger.info("Shutting down polling services...")
        if web_runner:
            await web_runner.cleanup()
        scheduler.shutdown(wait=False)
        await close_db()
        await bot.session.close()
        logger.info("Polling shutdown completed cleanly.")


async def main() -> None:
    """Initialize resources and choose Webhook or Polling mode."""
    logger.info("Initializing Clash Rack Rental Telegram Bot...")
    logger.info("Brand: %s | Bot Username: %s", settings.brand_name, settings.bot_username)

    # 1. Initialize Database Schema and seed defaults
    try:
        await init_db()
    except Exception as exc:
        logger.critical("Database initialization failed: %s", exc, exc_info=True)
        sys.exit(1)

    # 2. Setup Aiogram Bot & Dispatcher
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode="HTML")
    )
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    # 3. Register Middlewares in proper execution order
    dp.update.outer_middleware(DbSessionMiddleware())
    dp.update.outer_middleware(AuthMiddleware())
    dp.update.outer_middleware(MaintenanceMiddleware())
    dp.update.outer_middleware(ChannelJoinMiddleware())

    # 4. Include Master Router
    dp.include_router(main_router)

    # 5. Background Scheduler
    scheduler = setup_scheduler(bot)

    # 6. Set Commands
    await set_bot_commands(bot)

    # 7. Check if running on cloud PaaS with public URL (Render / Koyeb / Webhook)
    webhook_url = (
        os.environ.get("RENDER_EXTERNAL_URL")
        or os.environ.get("WEBHOOK_URL")
        or ("https://clash-rack-bot.onrender.com" if os.environ.get("PORT") else None)
    )
    port_env = os.environ.get("PORT")
    port = int(port_env) if port_env and port_env.isdigit() else 8080

    if webhook_url:
        logger.info("Detected cloud PaaS environment. Starting Webhook mode with URL: %s", webhook_url)
        await run_webhook(bot, dp, scheduler, webhook_url=webhook_url, port=port)
    else:
        logger.info("Starting Polling mode...")
        await run_polling(bot, dp, scheduler, port=None)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot process interrupted. Exiting.")
