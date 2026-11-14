"""Application Entry Point and Lifecycle Manager."""

import asyncio
import logging
import os
import sys
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

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


async def main() -> None:
    """Initialize resources and start Telegram bot polling."""
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

    # 5. Start Background Job Scheduler
    scheduler = setup_scheduler(bot)
    scheduler.start()
    logger.info("Background APScheduler started.")

    # 6. Set Commands
    await set_bot_commands(bot)

    # 7. Start Polling
    logger.info("Bot is now listening for Telegram updates...")
    try:
        # Discard old pending messages on boot
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    except Exception as exc:
        logger.error("Fatal error during polling: %s", exc, exc_info=True)
    finally:
        logger.info("Shutting down bot services...")
        scheduler.shutdown(wait=False)
        await close_db()
        await bot.session.close()
        logger.info("Bot shutdown completed cleanly.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot process interrupted by user. Exiting.")
