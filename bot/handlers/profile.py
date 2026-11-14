"""User Profile and Order History Handlers."""

import logging
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import User
from bot.keyboards.inline_user import get_user_orders_keyboard
from bot.keyboards.reply import MAIN_MENU_TEXTS
from bot.services.order_service import OrderService
from bot.services.user_service import UserService
from bot.states.user_states import SupportStates
from bot.utils.formatters import format_datetime, format_price

logger = logging.getLogger(__name__)

router = Router(name="profile_router")


@router.message(F.text == MAIN_MENU_TEXTS["profile"])
async def handle_user_profile(message: Message, session: AsyncSession) -> None:
    """Display user profile dashboard and aggregate account statistics."""
    stats = await UserService.get_user_stats(session, message.from_user.id)
    user: User = stats.get("user")

    if not user:
        await message.answer("❌ اطلاعات حساب کاربری شما یافت نشد.")
        return

    status_tag = "⛔️ مسدود شده" if user.is_blocked else "🟢 عادی و فعال"
    username_display = f"@{user.username}" if user.username else "ثبت نشده"

    text = (
        f"👤 <b>پروفایل کاربری شما</b>\n\n"
        f"▫️ نام: <b>{user.full_name}</b>\n"
        f"▫️ نام کاربری: {username_display}\n"
        f"▫️ شناسه عددی تلگرام: <code>{user.id}</code>\n"
        f"▫️ وضعیت حساب: <b>{status_tag}</b>\n"
        f"▫️ تاریخ عضویت: {format_datetime(user.created_at, include_time=False)}\n\n"
        f"📊 <b>آمار و سوابق فعالیت:</b>\n"
        f"▫️ تعداد کل سفارش‌ها: <b>{stats.get('total_orders')}</b>\n"
        f"▫️ سفارش‌های فعال کنونی: <b>{stats.get('active_orders')}</b>\n"
        f"▫️ مجموع پرداخت‌ها: <b>{format_price(stats.get('total_spent'))}</b>\n\n"
        f"⚡️ جهت مشاهده جزئیات سفارش‌های خود، گزینه «📦 سفارش‌های من» را انتخاب کنید."
    )

    await message.answer(text, parse_mode="HTML")


@router.message(F.text == MAIN_MENU_TEXTS["my_orders"])
async def handle_my_orders(message: Message, session: AsyncSession) -> None:
    """Show list of orders placed by the user."""
    orders = await OrderService.get_user_orders(session, message.from_user.id)
    if not orders:
        await message.answer(
            "📦 شما هنوز هیچ سفارشی در سامانه ثبت نکرده‌اید.\n"
            "از طریق گزینه «⚡ اجاره رک کلش» می‌توانید رک مورد نظر خود را سفارش دهید."
        )
        return

    text = (
        "📦 <b>تاریخچه و وضعیت سفارش‌های شما:</b>\n\n"
        "جهت مشاهده اطلاعات تکمیلی، تمدید یا پرداخت هر سفارش، روی آن کلیک فرمایید:"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=get_user_orders_keyboard(orders))


@router.callback_query(F.data == "my_orders_list")
async def handle_my_orders_callback(query: CallbackQuery, session: AsyncSession) -> None:
    """Callback to return to user orders list."""
    orders = await OrderService.get_user_orders(session, query.from_user.id)
    text = (
        "📦 <b>تاریخچه و وضعیت سفارش‌های شما:</b>\n\n"
        "روی سفارش مورد نظر جهت مشاهده جزئیات کلیک کنید:"
    )
    try:
        await query.message.edit_text(text, parse_mode="HTML", reply_markup=get_user_orders_keyboard(orders))
    except Exception:
        await query.message.answer(text, parse_mode="HTML", reply_markup=get_user_orders_keyboard(orders))
    await query.answer()


@router.callback_query(F.data.startswith("renew_order_user:"))
async def handle_renew_order_user(query: CallbackQuery, session: AsyncSession) -> None:
    """Notify user about order renewal."""
    order_id = int(query.data.split(":")[1])
    order = await OrderService.get_order_by_id(session, order_id)

    if not order:
        await query.answer("❌ سفارش یافت نشد.", show_alert=True)
        return

    await query.answer(
        f"جهت تمدید سفارش {order.order_code}، لطفاً از طریق بخش پشتیبانی به ادمین پیام دهید.",
        show_alert=True
    )


@router.callback_query(F.data.startswith("support_order:"))
async def handle_support_order(
    query: CallbackQuery,
    state: FSMContext
) -> None:
    """Open new support ticket pre-filled with order code."""
    order_code = query.data.split(":")[1]
    await state.update_data(ticket_subject=f"پیگیری سفارش {order_code}")
    await state.set_state(SupportStates.entering_message)

    text = (
        f"💬 شما در حال ارسال پیام پشتیبانی در خصوص سفارش <code>{order_code}</code> هستید.\n\n"
        f"لطفاً <b>متن پیام یا سوال خود</b> را ارسال فرمایید (می‌توانید عکس نیز ارسال کنید):"
    )
    await query.message.answer(text, parse_mode="HTML")
    await query.answer()
