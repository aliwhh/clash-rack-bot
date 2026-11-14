"""Admin User Profile, Search, and Blocking Handlers."""

import logging
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.inline_admin import get_admin_user_actions_keyboard, get_admin_users_keyboard
from bot.keyboards.inline_user import get_user_orders_keyboard
from bot.keyboards.reply import get_cancel_keyboard
from bot.services.order_service import OrderService
from bot.services.user_service import UserService
from bot.states.admin_states import AdminUserStates
from bot.utils.formatters import format_datetime, format_price

logger = logging.getLogger(__name__)

router = Router(name="admin_users_router")


@router.callback_query(F.data == "adm_users")
async def handle_adm_users(query: CallbackQuery, session: AsyncSession) -> None:
    """List recent users in admin."""
    is_admin = await UserService.is_admin(session, query.from_user.id)
    if not is_admin:
        await query.answer("دسترسی غیرمجاز.", show_alert=True)
        return

    users, total = await UserService.list_users(session, limit=20)
    text = (
        f"👥 <b>مدیریت کاربران سامانه ({total} نفر)</b>\n\n"
        "جهت مشاهده اطلاعات، سفارش‌ها یا مسدودسازی، روی کاربر کلیک کنید:"
    )

    markup = get_admin_users_keyboard(users)
    try:
        await query.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    except Exception:
        await query.message.answer(text, parse_mode="HTML", reply_markup=markup)
    await query.answer()


@router.callback_query(F.data == "adm_user_search")
async def handle_adm_user_search(query: CallbackQuery, state: FSMContext) -> None:
    """Prompt admin for user search keyword."""
    await state.set_state(AdminUserStates.search_query)
    await query.message.answer(
        "🔎 لطفاً <b>شناسه عددی تلگرام، نام یا یوزرنیم کاربر</b> را وارد فرمایید:",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()
    )
    await query.answer()


@router.message(AdminUserStates.search_query)
async def handle_user_search_input(
    message: Message,
    state: FSMContext,
    session: AsyncSession
) -> None:
    """Execute user search."""
    query_str = message.text.strip()
    users, total = await UserService.list_users(session, limit=20, search_query=query_str)
    await state.clear()

    if not users:
        await message.answer(f"❌ کاربری با مشخصات «{query_str}» یافت نشد.")
        return

    text = f"🔎 نتایج جستجو برای «{query_str}» ({total} مورد):"
    await message.answer(text, reply_markup=get_admin_users_keyboard(users))


@router.callback_query(F.data.startswith("adm_user_view:"))
async def handle_adm_user_view(query: CallbackQuery, session: AsyncSession) -> None:
    """Display user profile in admin."""
    user_id = int(query.data.split(":")[1])
    stats = await UserService.get_user_stats(session, user_id)
    user = stats.get("user")

    if not user:
        await query.answer("کاربر یافت نشد.", show_alert=True)
        return

    block_status = "⛔️ مسدود شده" if user.is_blocked else "🟢 فعال"

    text = (
        f"👤 <b>پروفایل کاربر: {user.full_name}</b>\n\n"
        f"▫️ شناسه عددی: <code>{user.id}</code>\n"
        f"▫️ نام کاربری: @{user.username or 'ندارد'}\n"
        f"▫️ وضعیت: <b>{block_status}</b>\n"
        f"▫️ تاریخ عضویت: {format_datetime(user.created_at)}\n\n"
        f"📊 <b>آمار سفارش‌ها:</b>\n"
        f"▫️ تعداد سفارش‌ها: <b>{stats.get('total_orders')}</b>\n"
        f"▫️ سفارش‌های فعال: <b>{stats.get('active_orders')}</b>\n"
        f"▫️ مجموع واریزی‌ها: <b>{format_price(stats.get('total_spent'))}</b>\n"
    )

    markup = get_admin_user_actions_keyboard(user)
    try:
        await query.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    except Exception:
        await query.message.answer(text, parse_mode="HTML", reply_markup=markup)
    await query.answer()


@router.callback_query(F.data.startswith("adm_user_toggle_block:"))
async def handle_adm_user_toggle_block(query: CallbackQuery, session: AsyncSession) -> None:
    """Toggle user block status."""
    user_id = int(query.data.split(":")[1])
    user = await UserService.get_user(session, user_id)
    if not user:
        await query.answer("کاربر یافت نشد.", show_alert=True)
        return

    new_status = not user.is_blocked
    await UserService.set_block_status(session, user_id, new_status)
    status_label = "مسدود" if new_status else "رفع مسدودیت"
    await query.answer(f"کاربر با موفقیت {status_label} شد.", show_alert=True)

    # Refresh
    updated_user = await UserService.get_user(session, user_id)
    try:
        await query.message.edit_reply_markup(reply_markup=get_admin_user_actions_keyboard(updated_user))
    except Exception:
        pass


@router.callback_query(F.data.startswith("adm_user_orders:"))
async def handle_adm_user_orders(query: CallbackQuery, session: AsyncSession) -> None:
    """View orders of a specific user."""
    user_id = int(query.data.split(":")[1])
    orders = await OrderService.get_user_orders(session, user_id)

    if not orders:
        await query.answer("این کاربر هنوز سفارشی ثبت نکرده است.", show_alert=True)
        return

    text = f"📦 <b>سفارش‌های کاربر {user_id}:</b>"
    try:
        await query.message.edit_text(text, parse_mode="HTML", reply_markup=get_user_orders_keyboard(orders))
    except Exception:
        await query.message.answer(text, parse_mode="HTML", reply_markup=get_user_orders_keyboard(orders))
    await query.answer()
