"""Mandatory Channel Subscription Enforcement Middleware."""

import logging
from typing import Any, Awaitable, Callable, Dict, List
from aiogram import BaseMiddleware, Bot
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    TelegramObject,
)

from bot.config import settings
from bot.database.models import Channel
from bot.services.settings_service import SettingsService

logger = logging.getLogger(__name__)


class ChannelJoinMiddleware(BaseMiddleware):
    """Enforces mandatory channel subscriptions before accessing bot features."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        session = data.get("session")
        bot: Bot = data.get("bot")

        event_user = data.get("event_from_user")
        user_id = event_user.id if event_user else None

        if not user_id:
            if isinstance(event, Message) and event.from_user:
                user_id = event.from_user.id
            elif isinstance(event, CallbackQuery) and event.from_user:
                user_id = event.from_user.id
            elif hasattr(event, "message") and event.message and event.message.from_user:
                user_id = event.message.from_user.id
            elif hasattr(event, "callback_query") and event.callback_query and event.callback_query.from_user:
                user_id = event.callback_query.from_user.id

        # Allow /start message without blocking so greeting and main menu can be displayed
        msg_text = None
        if isinstance(event, Message) and event.text:
            msg_text = event.text
        elif hasattr(event, "message") and event.message and event.message.text:
            msg_text = event.message.text

        if msg_text and msg_text.startswith("/start"):
            return await handler(event, data)

        # Allow check_membership callback
        cb_data = None
        if isinstance(event, CallbackQuery) and event.data:
            cb_data = event.data
        elif hasattr(event, "callback_query") and event.callback_query and event.callback_query.data:
            cb_data = event.callback_query.data

        if cb_data == "check_membership":
            return await handler(event, data)

        if not user_id or not session or not bot:
            return await handler(event, data)

        # Bypass for administrators
        if settings.is_admin(user_id):
            return await handler(event, data)

        channels: List[Channel] = await SettingsService.get_mandatory_channels(session, active_only=True)
        if not channels:
            return await handler(event, data)

        unsubscribed_channels: List[Channel] = []
        for channel in channels:
            try:
                chat_member = await bot.get_chat_member(chat_id=channel.channel_id, user_id=user_id)
                # Valid statuses: creator, administrator, member
                if chat_member.status not in ["creator", "administrator", "member"]:
                    unsubscribed_channels.append(channel)
            except Exception as exc:
                # If bot cannot check or was not added to channel as admin, log warning
                logger.warning("Failed to check membership for %s (user %d): %s", channel.channel_id, user_id, exc)

        if unsubscribed_channels:
            keyboard_buttons = []
            for ch in unsubscribed_channels:
                keyboard_buttons.append([
                    InlineKeyboardButton(text=f"📢 عضویت در {ch.channel_name}", url=ch.invite_link)
                ])
            keyboard_buttons.append([
                InlineKeyboardButton(text="✅ بررسی عضویت", callback_data="check_membership")
            ])
            markup = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

            warning_text = (
                "⚠️ <b>توجه: عضویت در کانال‌های زیر الزامی است</b>\n\n"
                "برای استفاده از امکانات ربات، ابتدا در کانال‌های زیر عضو شوید و سپس دکمه <b>بررسی عضویت</b> را انتخاب کنید."
            )

            if isinstance(event, Message):
                await event.answer(warning_text, parse_mode="HTML", reply_markup=markup)
            elif isinstance(event, CallbackQuery):
                await event.message.answer(warning_text, parse_mode="HTML", reply_markup=markup)
                await event.answer("ابتدا عضو کانال‌ها شوید.", show_alert=True)
            return

        return await handler(event, data)
