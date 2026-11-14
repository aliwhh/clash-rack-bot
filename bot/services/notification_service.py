"""System Notification and Telegram Dispatcher Service."""

import logging
from typing import Any, Optional

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup

from bot.config import settings
from bot.database.models import Order, Payment, SupportMessage, SupportTicket
from bot.utils.formatters import format_datetime, format_price

logger = logging.getLogger(__name__)


class NotificationService:
    """Dispatches notifications to users and administrators for key business events."""

    @staticmethod
    async def send_user_notification(
        bot: Bot,
        user_id: int,
        text: str,
        reply_markup: Optional[InlineKeyboardMarkup] = None
    ) -> bool:
        """Safely send a notification message to a Telegram user."""
        try:
            await bot.send_message(
                chat_id=user_id,
                text=text,
                parse_mode="HTML",
                reply_markup=reply_markup,
            )
            return True
        except Exception as exc:
            logger.warning("Failed to send notification to user %d: %s", user_id, exc)
            return False

    @staticmethod
    async def broadcast_to_admins(
        bot: Bot,
        text: str,
        reply_markup: Optional[InlineKeyboardMarkup] = None
    ) -> int:
        """Broadcast an alert message to all configured administrators."""
        success_count = 0
        for admin_id in settings.admin_id_list:
            try:
                await bot.send_message(
                    chat_id=admin_id,
                    text=text,
                    parse_mode="HTML",
                    reply_markup=reply_markup,
                )
                success_count += 1
            except Exception as exc:
                logger.warning("Failed to dispatch alert to admin %d: %s", admin_id, exc)
        return success_count

    @staticmethod
    async def notify_order_created(bot: Bot, order: Order) -> None:
        """Notify admins about new order creation."""
        text = (
            f"🛒 <b>سفارش جدید ثبت شد!</b>\n\n"
            f"▫️ کد سفارش: <code>{order.order_code}</code>\n"
            f"▫️ کاربر: <code>{order.user_id}</code>\n"
            f"▫️ رک: <b>{order.rack.name}</b>\n"
            f"▫️ پلن: {order.plan.title} ({order.plan.duration_hours} ساعت)\n"
            f"▫️ مبلغ نهایی: <b>{format_price(order.final_price)}</b>\n"
            f"▫️ روش پرداخت: {order.payment_method.value}\n"
            f"▫️ تگ پلیر: {order.player_tag or 'ثبت نشده'}\n"
            f"▫️ زمان: {format_datetime(order.created_at)}"
        )
        await NotificationService.broadcast_to_admins(bot, text)

    @staticmethod
    async def notify_card_to_card_pending(bot: Bot, order: Order, payment: Payment) -> None:
        """Send card-to-card receipt alert with photo to admins."""
        caption = (
            f"💳 <b>رسید کارت به کارت جدید جهت بررسی!</b>\n\n"
            f"▫️ کد سفارش: <code>{order.order_code}</code>\n"
            f"▫️ شناسه پرداخت: <code>{payment.id}</code>\n"
            f"▫️ کاربر: <code>{order.user_id}</code>\n"
            f"▫️ مبلغ: <b>{format_price(payment.amount)}</b>\n"
            f"▫️ رک: <b>{order.rack.name}</b>\n\n"
            f"⚠️ لطفاً از بخش مدیریت سفارش‌ها در پنل ادمین، رسید را بررسی و تأیید یا رد نمایید."
        )

        for admin_id in settings.admin_id_list:
            try:
                if payment.receipt_photo_id:
                    await bot.send_photo(
                        chat_id=admin_id,
                        photo=payment.receipt_photo_id,
                        caption=caption,
                        parse_mode="HTML"
                    )
                else:
                    await bot.send_message(
                        chat_id=admin_id,
                        text=caption,
                        parse_mode="HTML"
                    )
            except Exception as exc:
                logger.warning("Failed to send receipt alert to admin %d: %s", admin_id, exc)

    @staticmethod
    async def notify_order_approved(bot: Bot, order: Order) -> None:
        """Notify user that rental order has been approved and activated."""
        text = (
            f"🎉 <b>سفارش شما با موفقیت تأیید و فعال شد!</b>\n\n"
            f"▫️ کد پیگیری سفارش: <code>{order.order_code}</code>\n"
            f"▫️ سرویس: <b>{order.rack.name}</b>\n"
            f"▫️ تگ کلن: <code>{order.rack.clan_tag or 'ندارد'}</code>\n"
            f"▫️ تاریخ شروع: {format_datetime(order.start_date)}\n"
            f"▫️ تاریخ پایان: {format_datetime(order.end_date)}\n\n"
            f"⚡️ هم‌اکنون می‌توانید وارد کلن شده و از خدمات دونیت و رک لذت ببرید.\n"
            f"در صورت نیاز به راهنمایی، از منوی ربات با پشتیبانی در ارتباط باشید."
        )
        await NotificationService.send_user_notification(bot, order.user_id, text)

    @staticmethod
    async def notify_new_ticket(bot: Bot, ticket: SupportTicket, initial_text: Optional[str]) -> None:
        """Alert admins about a newly opened support ticket."""
        text = (
            f"📩 <b>تیکت پشتیبانی جدید!</b>\n\n"
            f"▫️ کد تیکت: <code>{ticket.ticket_code}</code>\n"
            f"▫️ کاربر: <code>{ticket.user_id}</code>\n"
            f"▫️ موضوع: <b>{ticket.subject}</b>\n"
            f"▫️ متن پیام: {initial_text or '(تصویر/فایل)'}\n\n"
            f"پاسخگویی از طریق پنل مدیریت امکان‌پذیر است."
        )
        await NotificationService.broadcast_to_admins(bot, text)

    @staticmethod
    async def notify_ticket_reply(bot: Bot, ticket: SupportTicket, msg: SupportMessage) -> None:
        """Notify customer when an admin replies to their ticket."""
        text = (
            f"💬 <b>پاسخ جدید از پشتیبانی!</b>\n\n"
            f"▫️ کد تیکت: <code>{ticket.ticket_code}</code>\n"
            f"▫️ موضوع: {ticket.subject}\n\n"
            f"✉️ <b>متن پاسخ:</b>\n{msg.text or ''}\n\n"
            f"جهت مشاهده گفتگو و ارسال پاسخ تکمیلی، به بخش «ارتباط با پشتیبانی» مراجعه فرمایید."
        )
        await NotificationService.send_user_notification(bot, ticket.user_id, text)
