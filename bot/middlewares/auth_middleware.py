"""User authentication and block-check middleware."""

import logging
from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from bot.services.user_service import UserService

logger = logging.getLogger(__name__)


class AuthMiddleware(BaseMiddleware):
    """Ensures user record exists and filters blocked users."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        session = data.get("session")
        telegram_user = None

        if isinstance(event, Message):
            telegram_user = event.from_user
        elif isinstance(event, CallbackQuery):
            telegram_user = event.from_user

        if telegram_user and session:
            user, _ = await UserService.get_or_create_user(
                session=session,
                user_id=telegram_user.id,
                full_name=telegram_user.full_name,
                username=telegram_user.username,
            )
            data["user"] = user

            # Block check
            if user.is_blocked:
                block_msg = "⛔️ حساب کاربری شما توسط مدیریت مسدود شده است."
                if isinstance(event, Message):
                    await event.answer(block_msg)
                elif isinstance(event, CallbackQuery):
                    await event.answer(block_msg, show_alert=True)
                return

        return await handler(event, data)
