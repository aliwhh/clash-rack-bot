"""Background periodic scheduled tasks using APScheduler."""

import logging
import os
import aiohttp
from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from bot.config import settings
from bot.database.session import get_session
from bot.services.notification_service import NotificationService
from bot.services.order_service import OrderService
from bot.utils.formatters import format_datetime

logger = logging.getLogger(__name__)


async def job_expire_temporary_reservations(bot: Bot) -> None:
    """Periodic job to free temporary reservations past hold deadline."""
    try:
        async with get_session() as session:
            count = await OrderService.cleanup_expired_reservations(session)
            if count > 0:
                logger.info("Scheduler: Released %d expired temporary reservations.", count)
    except Exception as exc:
        logger.error("Error in job_expire_temporary_reservations: %s", exc, exc_info=True)


async def job_expire_active_rentals(bot: Bot) -> None:
    """Periodic job to complete ended rentals, free racks, and notify renters."""
    try:
        async with get_session() as session:
            expired_orders = await OrderService.cleanup_expired_active_rentals(session)
            for order in expired_orders:
                notify_text = (
                    f"⌛️ <b>مهلت اجاره رک شما به پایان رسید.</b>\n\n"
                    f"▫️ کد سفارش: <code>{order.order_code}</code>\n"
                    f"▫️ سرویس: <b>{order.rack.name}</b>\n"
                    f"▫️ تاریخ پایان: {format_datetime(order.end_date)}\n\n"
                    f"از اینکه از خدمات {settings.brand_name} استفاده نمودید سپاسگزاریم.\n"
                    f"در صورت تمایل به تمدید یا رزرو مجدد، می‌توانید از منوی ربات اقدام فرمایید."
                )
                await NotificationService.send_user_notification(bot, order.user_id, notify_text)
    except Exception as exc:
        logger.error("Error in job_expire_active_rentals: %s", exc, exc_info=True)


async def job_send_rental_reminders(bot: Bot) -> None:
    """Periodic job to alert users whose rentals will end within reminder window."""
    try:
        async with get_session() as session:
            for hours in settings.reminder_hours_list:
                expiring_orders = await OrderService.get_expiring_rentals_for_reminder(session, hours_before=hours)
                for order in expiring_orders:
                    reminder_text = (
                        f"⏰ <b>یادآوری: نزدیک شدن به پایان مدت اجاره رک</b>\n\n"
                        f"▫️ کد سفارش: <code>{order.order_code}</code>\n"
                        f"▫️ سرویس: <b>{order.rack.name}</b>\n"
                        f"▫️ زمان پایان: <b>{format_datetime(order.end_date)}</b>\n\n"
                        f"⚠️ کمتر از {hours} ساعت تا اتمام مهلت این سرویس باقی مانده است.\n"
                        f"جهت تمدید اجاره و جلوگیری از آزادسازی رک، می‌توانید از طریق بخش پشتیبانی به ادمین پیام دهید."
                    )
                    await NotificationService.send_user_notification(bot, order.user_id, reminder_text)
    except Exception as exc:
        logger.error("Error in job_send_rental_reminders: %s", exc, exc_info=True)


async def job_keep_alive_ping(bot: Bot) -> None:
    """Self-ping healthcheck endpoint to keep Render Free instance warm and prevent spindown."""
    render_url = (
        os.environ.get("RENDER_EXTERNAL_URL")
        or os.environ.get("WEBHOOK_URL")
        or "https://clash-rack-bot.onrender.com"
    )
    if render_url:
        health_url = f"{render_url.rstrip('/')}/health"
        try:
            async with aiohttp.ClientSession() as client:
                async with client.get(health_url, timeout=10) as resp:
                    logger.debug("Keep-alive self-ping to %s status: %d", health_url, resp.status)
        except Exception as exc:
            logger.debug("Keep-alive ping failed: %s", exc)


def setup_scheduler(bot: Bot) -> AsyncIOScheduler:
    """Initialize and configure background AsyncIOScheduler."""
    scheduler = AsyncIOScheduler(timezone="UTC")

    # Clean temporary reservation holds every 60 seconds
    scheduler.add_job(
        job_expire_temporary_reservations,
        "interval",
        seconds=60,
        args=[bot],
        id="job_expire_temporary_reservations",
        replace_existing=True,
    )

    # Clean expired active rentals every 5 minutes
    scheduler.add_job(
        job_expire_active_rentals,
        "interval",
        minutes=5,
        args=[bot],
        id="job_expire_active_rentals",
        replace_existing=True,
    )

    # Check for reminders every 15 minutes
    scheduler.add_job(
        job_send_rental_reminders,
        "interval",
        minutes=15,
        args=[bot],
        id="job_send_rental_reminders",
        replace_existing=True,
    )

    # Keep alive self-ping every 10 minutes to prevent Render Free spindown
    scheduler.add_job(
        job_keep_alive_ping,
        "interval",
        minutes=10,
        args=[bot],
        id="job_keep_alive_ping",
        replace_existing=True,
    )

    return scheduler
