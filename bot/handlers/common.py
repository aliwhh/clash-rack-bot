"""Common and entrypoint handlers (/start, main navigation, rules, cancel)."""

import logging
from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.database.models import User
from bot.keyboards.reply import MAIN_MENU_TEXTS, get_main_menu_keyboard
from bot.services.settings_service import SettingsService
from bot.services.user_service import UserService

logger = logging.getLogger(__name__)

router = Router(name="common_router")


@router.message(CommandStart())
async def handle_start(message: Message, state: FSMContext, session: AsyncSession) -> None:
    """Handle /start command, clear any active state, and display welcome screen."""
    await state.clear()
    is_admin = await UserService.is_admin(session, message.from_user.id)

    # Fetch dynamic welcome text or fallback
    welcome_text = await SettingsService.get_setting(
        session, "welcome_message", default=settings.welcome_message
    )

    full_message = (
        f"سلام <b>{message.from_user.full_name}</b> عزیز ⚡️\n\n"
        f"{welcome_text}\n\n"
        f"🏷 <b>برند:</b> {settings.brand_name}\n"
        f"📌 جهت شروع، یکی از گزینه‌های زیر را انتخاب نمایید:"
    )

    await message.answer(
        full_message,
        parse_mode="HTML",
        reply_markup=get_main_menu_keyboard(is_admin=is_admin)
    )


@router.message(F.text == MAIN_MENU_TEXTS["cancel"])
async def handle_cancel_text(message: Message, state: FSMContext, session: AsyncSession) -> None:
    """Cancel any active FSM state and return to main menu."""
    await state.clear()
    is_admin = await UserService.is_admin(session, message.from_user.id)
    await message.answer(
        "❌ عملیات جاری لغو گردید. به منوی اصلی بازگشتید.",
        reply_markup=get_main_menu_keyboard(is_admin=is_admin)
    )


@router.callback_query(F.data == "back_to_main")
async def handle_back_to_main_callback(query: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    """Callback to return to main menu."""
    await state.clear()
    is_admin = await UserService.is_admin(session, query.from_user.id)
    await query.message.delete()
    await query.message.answer(
        "⚡️ به منوی اصلی بازگشتید.",
        reply_markup=get_main_menu_keyboard(is_admin=is_admin)
    )
    await query.answer()


@router.callback_query(F.data == "check_membership")
async def handle_check_membership(query: CallbackQuery, session: AsyncSession) -> None:
    """User clicked check membership button."""
    # The middleware will either intercept if not subscribed, or pass here if verified
    await query.answer("✅ عضویت شما در کانال‌ها با موفقیت تأیید شد!", show_alert=True)
    is_admin = await UserService.is_admin(session, query.from_user.id)
    await query.message.delete()
    await query.message.answer(
        "🎉 سپاس از عضویت شما. اکنون می‌توانید از تمام امکانات ربات استفاده کنید.",
        reply_markup=get_main_menu_keyboard(is_admin=is_admin)
    )


@router.message(F.text == MAIN_MENU_TEXTS["rules"])
async def handle_rules_message(message: Message, session: AsyncSession) -> None:
    """Display terms of service and rules."""
    rules_link = await SettingsService.get_setting(session, "rules_link", default=settings.rules_link)
    text = (
        f"📜 <b>قوانین و مقررات استفاده از خدمات {settings.brand_name}:</b>\n\n"
        f"۱. استفاده از رک‌ها صرفاً جهت دونیت، شرکت در کلن وار و پیشرفت اکانت بازی می‌باشد.\n"
        f"۲. هرگونه سوءاستفاده یا تغییر تنظیمات غیرمجاز در کلن ممنوع بوده و موجب مسدودیت سرویس بدون بازگشت وجه خواهد شد.\n"
        f"۳. مدت اجاره از لحظه تأیید و تحویل سفارش محاسبه می‌گردد.\n"
        f"۴. امکان تمدید سرویس پیش از اتمام مهلت از طریق بخش «سفارش‌های من» فراهم است.\n\n"
        f"🔗 جهت مطالعه قوانین کامل: <a href='{rules_link}'>مشاهده مرام‌نامه و مقررات</a>"
    )
    await message.answer(text, parse_mode="HTML", disable_web_page_preview=True)
