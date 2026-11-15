"""Maintenance mode gatekeeper middleware."""

from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from bot.config import settings
from bot.services.settings_service import SettingsService


class MaintenanceMiddleware(BaseMiddleware):
    """Halts standard user interactions when maintenance mode is active."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        session = data.get("session")
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

        # Admins always bypass maintenance mode
        if user_id and settings.is_admin(user_id):
            return await handler(event, data)

        if session:
            is_maintenance = await SettingsService.is_maintenance_mode(session)
            if is_maintenance:
                msg_text = (
                    "🚧 <b>سامانه در حال بروزرسانی و تعمیرات می‌باشد.</b>\n\n"
                    "لطفاً ساعاتی دیگر مجدداً مراجعه فرمایید.\n"
                    "از شکیبایی شما سپاسگزاریم."
                )
                if isinstance(event, Message):
                    await event.answer(msg_text, parse_mode="HTML")
                elif isinstance(event, CallbackQuery):
                    await event.answer("🚧 سامانه موقتاً در حال تعمیرات است.", show_alert=True)
                return

        return await handler(event, data)
