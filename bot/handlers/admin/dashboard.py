"""Admin Dashboard and Statistics Handlers."""

import logging
from datetime import datetime, timezone
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import (
    Order,
    OrderStatus,
    Payment,
    PaymentStatus,
    Rack,
    RackStatus,
    SupportTicket,
    TicketStatus,
    User,
)
from bot.keyboards.inline_admin import get_admin_dashboard_keyboard
from bot.keyboards.reply import MAIN_MENU_TEXTS
from bot.services.user_service import UserService
from bot.utils.formatters import format_price

logger = logging.getLogger(__name__)

router = Router(name="admin_dashboard_router")


async def get_system_stats(session: AsyncSession) -> dict:
    """Calculate live metrics and statistics across all database tables."""
    now_utc = datetime.now(timezone.utc)
    today_start = datetime(now_utc.year, now_utc.month, now_utc.day, tzinfo=timezone.utc)

    # Users count
    total_users = (await session.execute(select(func.count(User.id)))).scalar() or 0
    today_users = (
        await session.execute(select(func.count(User.id)).where(User.created_at >= today_start))
    ).scalar() or 0

    # Orders count
    total_orders = (await session.execute(select(func.count(Order.id)))).scalar() or 0
    pending_orders = (
        await session.execute(
            select(func.count(Order.id)).where(
                Order.status.in_([OrderStatus.PENDING_APPROVAL, OrderStatus.PENDING_PAYMENT])
            )
        )
    ).scalar() or 0
    active_orders = (
        await session.execute(select(func.count(Order.id)).where(Order.status == OrderStatus.ACTIVE))
    ).scalar() or 0

    # Racks count
    available_racks = (
        await session.execute(
            select(func.count(Rack.id)).where(
                Rack.is_active.is_(True),
                Rack.status == RackStatus.AVAILABLE
            )
        )
    ).scalar() or 0

    # Revenue
    total_rev = (
        await session.execute(
            select(func.sum(Payment.amount)).where(Payment.status == PaymentStatus.SUCCESSFUL)
        )
    ).scalar() or 0
    today_rev = (
        await session.execute(
            select(func.sum(Payment.amount)).where(
                Payment.status == PaymentStatus.SUCCESSFUL,
                Payment.created_at >= today_start
            )
        )
    ).scalar() or 0

    # Tickets
    open_tickets = (
        await session.execute(
            select(func.count(SupportTicket.id)).where(
                SupportTicket.status.in_([TicketStatus.OPEN, TicketStatus.IN_PROGRESS])
            )
        )
    ).scalar() or 0

    return {
        "total_users": total_users,
        "today_users": today_users,
        "total_orders": total_orders,
        "pending_orders": pending_orders,
        "active_orders": active_orders,
        "available_racks": available_racks,
        "total_rev": int(total_rev),
        "today_rev": int(today_rev),
        "open_tickets": open_tickets,
    }


def render_dashboard_text(stats: dict) -> str:
    """Render HTML formatted dashboard summary."""
    return (
        f"👑 <b>پنل مدیریت و مانیتورینگ ربات</b>\n\n"
        f"👥 <b>کاربران:</b>\n"
        f"▫️ کل کاربران: <b>{stats['total_users']:,}</b> نفر\n"
        f"▫️ اعضای امروز: <b>{stats['today_users']:,}</b> نفر\n\n"
        f"📦 <b>سفارش‌ها و اجاره‌ها:</b>\n"
        f"▫️ کل سفارش‌ها: <b>{stats['total_orders']:,}</b>\n"
        f"▫️ در انتظار بررسی/پرداخت: <b>{stats['pending_orders']:,}</b> ⏳\n"
        f"▫️ اجاره‌های فعال: <b>{stats['active_orders']:,}</b> 🟢\n"
        f"▫️ رک‌های آماده اجاره: <b>{stats['available_racks']:,}</b> عدد\n\n"
        f"💰 <b>آمار مالی و درآمد:</b>\n"
        f"▫️ درآمد کل: <b>{format_price(stats['total_rev'])}</b>\n"
        f"▫️ درآمد امروز: <b>{format_price(stats['today_rev'])}</b>\n\n"
        f"📩 <b>پشتیبانی:</b>\n"
        f"▫️ تیکت‌های نیازمند پاسخ: <b>{stats['open_tickets']:,}</b>\n\n"
        f"⚙️ جهت مدیریت هر بخش از دکمه‌های زیر استفاده فرمایید:"
    )


@router.message(Command("admin"))
@router.message(F.text == MAIN_MENU_TEXTS["admin"])
async def handle_admin_entry(
    message: Message,
    state: FSMContext,
    session: AsyncSession
) -> None:
    """Enter administrator panel if authorized."""
    await state.clear()
    is_admin = await UserService.is_admin(session, message.from_user.id)
    if not is_admin:
        await message.answer("⛔️ دسترسی به پنل مدیریت صرفاً برای مدیران مجاز امکان‌پذیر است.")
        return

    stats = await get_system_stats(session)
    await message.answer(
        render_dashboard_text(stats),
        parse_mode="HTML",
        reply_markup=get_admin_dashboard_keyboard()
    )


@router.callback_query(F.data == "adm_dashboard")
async def handle_admin_dashboard_callback(
    query: CallbackQuery,
    state: FSMContext,
    session: AsyncSession
) -> None:
    """Return to admin main dashboard."""
    await state.clear()
    is_admin = await UserService.is_admin(session, query.from_user.id)
    if not is_admin:
        await query.answer("دسترسی غیرمجاز.", show_alert=True)
        return

    stats = await get_system_stats(session)
    try:
        await query.message.edit_text(
            render_dashboard_text(stats),
            parse_mode="HTML",
            reply_markup=get_admin_dashboard_keyboard()
        )
    except Exception:
        await query.message.answer(
            render_dashboard_text(stats),
            parse_mode="HTML",
            reply_markup=get_admin_dashboard_keyboard()
        )
    await query.answer()
