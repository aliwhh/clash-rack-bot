"""Admin Mass Broadcast Messaging Handlers."""

import asyncio
import logging
from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import User
from bot.keyboards.reply import get_cancel_keyboard
from bot.services.user_service import UserService
from bot.states.admin_states import AdminBroadcastStates

logger = logging.getLogger(__name__)

router = Router(name="admin_broadcast_router")


@router.callback_query(F.data == "adm_broadcast")
async def handle_adm_broadcast(query: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    """Prompt admin for broadcast message."""
    is_admin = await UserService.is_admin(session, query.from_user.id)
    if not is_admin:
        await query.answer("دسترسی غیرمجاز.", show_alert=True)
        return

    await state.set_state(AdminBroadcastStates.message_content)
    await query.message.answer(
        "📢 <b>ارسال پیام همگانی به تمام اعضای ربات</b>\n\n"
        "لطفاً متن، تصویر یا پیام اطلاعیه‌ای که مایلید برای تمام کاربران فرستاده شود را ارسال نمایید:",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()
    )
    await query.answer()


@router.message(AdminBroadcastStates.message_content)
async def handle_broadcast_message_input(message: Message, state: FSMContext) -> None:
    """Store broadcast content and request confirmation."""
    text = message.text or message.caption
    photo_id = message.photo[-1].file_id if message.photo else None

    await state.update_data(text=text, photo_id=photo_id)
    await state.set_state(AdminBroadcastStates.confirm_send)

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🚀 بله، هم‌اکنون ارسال کن", callback_data="confirm_broadcast_yes"),
            InlineKeyboardButton(text="❌ لغو ارسال", callback_data="adm_dashboard"),
        ]
    ])

    await message.answer(
        "⚠️ <b>تأییدیه ارسال پیام همگانی</b>\n\n"
        "آیا از ارسال پیام فوق به تمامی کاربران ربات اطمینان دارید؟",
        parse_mode="HTML",
        reply_markup=markup
    )


@router.callback_query(F.data == "confirm_broadcast_yes")
async def handle_broadcast_confirm(
    query: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot
) -> None:
    """Execute broadcast loop to all registered users."""
    data = await state.get_data()
    text = data.get("text", "")
    photo_id = data.get("photo_id")
    await state.clear()

    # Fetch all user IDs
    stmt = select(User.id).where(User.is_blocked.is_(False))
    user_ids = list((await session.execute(stmt)).scalars().all())

    status_msg = await query.message.answer(f"⏳ در حال ارسال پیام به {len(user_ids)} کاربر...")

    success_count = 0
    fail_count = 0

    for uid in user_ids:
        try:
            if photo_id:
                await bot.send_photo(chat_id=uid, photo=photo_id, caption=text, parse_mode="HTML")
            else:
                await bot.send_message(chat_id=uid, text=text, parse_mode="HTML")
            success_count += 1
            await asyncio.sleep(0.05)  # Telegram rate limit compliance
        except Exception:
            fail_count += 1

    report_text = (
        f"📊 <b>گزارش ارسال پیام همگانی به پایان رسید:</b>\n\n"
        f"▫️ کل کاربران هدف: <b>{len(user_ids)}</b>\n"
        f"▫️ ارسال‌های موفق: <b>{success_count}</b> ✅\n"
        f"▫️ ارسال‌های ناموفق (مسدود یا حذف): <b>{fail_count}</b> ❌"
    )
    await status_msg.edit_text(report_text, parse_mode="HTML")
    await query.answer()
