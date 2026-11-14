"""Admin Bot Configuration, Channels, and Excel Export Handlers."""

import io
import logging
from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from openpyxl import Workbook
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bot.database.models import Order
from bot.keyboards.inline_admin import (
    get_admin_channels_keyboard,
    get_admin_settings_keyboard,
)
from bot.keyboards.reply import get_cancel_keyboard
from bot.services.settings_service import SettingsService
from bot.services.user_service import UserService
from bot.states.admin_states import AdminSettingsStates

logger = logging.getLogger(__name__)

router = Router(name="admin_settings_router")


@router.callback_query(F.data == "adm_settings")
async def handle_adm_settings(query: CallbackQuery, session: AsyncSession) -> None:
    """Show bot settings management menu."""
    is_admin = await UserService.is_admin(session, query.from_user.id)
    if not is_admin:
        await query.answer("دسترسی غیرمجاز.", show_alert=True)
        return

    is_maint = await SettingsService.is_maintenance_mode(session)
    text = (
        "⚙️ <b>تنظیمات پیشرفته ربات و زیرساخت</b>\n\n"
        f"▫️ وضعیت حالت تعمیرات: <b>{'فعال (ربات مسدود برای کاربران عادی)' if is_maint else 'غیرفعال (ربات در دسترس)'}</b>\n\n"
        "جهت تغییر هر یک از موارد زیر اقدام فرمایید:"
    )

    markup = get_admin_settings_keyboard(is_maint)
    try:
        await query.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    except Exception:
        await query.message.answer(text, parse_mode="HTML", reply_markup=markup)
    await query.answer()


@router.callback_query(F.data == "adm_toggle_maintenance")
async def handle_toggle_maintenance(query: CallbackQuery, session: AsyncSession) -> None:
    """Toggle system maintenance mode."""
    is_maint = await SettingsService.is_maintenance_mode(session)
    new_status = "false" if is_maint else "true"
    await SettingsService.set_setting(session, "maintenance_mode", new_status)

    state_text = "غیرفعال" if is_maint else "فعال"
    await query.answer(f"حالت تعمیرات {state_text} شد.", show_alert=True)

    # Refresh
    updated_maint = await SettingsService.is_maintenance_mode(session)
    try:
        await query.message.edit_reply_markup(reply_markup=get_admin_settings_keyboard(updated_maint))
    except Exception:
        pass


@router.callback_query(F.data == "adm_channels")
async def handle_adm_channels(query: CallbackQuery, session: AsyncSession) -> None:
    """List mandatory membership channels."""
    channels = await SettingsService.get_mandatory_channels(session, active_only=False)
    text = (
        "📢 <b>مدیریت کانال‌های عضویت اجباری</b>\n\n"
        "در صورتی که کانالی در این لیست وجود داشته باشد، کاربران قبل از استفاده باید عضو آن شوند:"
    )
    markup = get_admin_channels_keyboard(channels)
    try:
        await query.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    except Exception:
        await query.message.answer(text, parse_mode="HTML", reply_markup=markup)
    await query.answer()


@router.callback_query(F.data == "adm_channel_add")
async def handle_adm_channel_add(query: CallbackQuery, state: FSMContext) -> None:
    """Prompt for mandatory channel username/ID."""
    await state.set_state(AdminSettingsStates.add_channel_id)
    await query.message.answer(
        "➕ <b>افزودن کانال عضویت اجباری</b>\n\n"
        "لطفاً <b>آیدی عمومی یا شناسه عددی کانال</b> را وارد کنید (مثال: @clash_rack یا -100123456789):\n\n"
        "⚠️ <i>توجه: ربات حتماً باید در کانال مذکور ادمین باشد تا بتواند عضویت کاربر را استعلام کند.</i>",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()
    )
    await query.answer()


@router.message(AdminSettingsStates.add_channel_id)
async def handle_channel_id_input(message: Message, state: FSMContext) -> None:
    """Store channel ID and ask for channel title."""
    ch_id = message.text.strip()
    await state.update_data(ch_id=ch_id)
    await state.set_state(AdminSettingsStates.add_channel_name)
    await message.answer("لطفاً <b>نام نمایشی کانال</b> را وارد فرمایید (مثال: کانال رسمی کلش رک):", parse_mode="HTML")


@router.message(AdminSettingsStates.add_channel_name)
async def handle_channel_name_input(message: Message, state: FSMContext) -> None:
    """Store channel title and ask for invite link."""
    name = message.text.strip()
    await state.update_data(ch_name=name)
    await state.set_state(AdminSettingsStates.add_channel_link)
    await message.answer("لطفاً <b>لینک دعوت کانال</b> را وارد نمایید (مثال: https://t.me/clash_rack):", parse_mode="HTML")


@router.message(AdminSettingsStates.add_channel_link)
async def handle_channel_link_input(
    message: Message,
    state: FSMContext,
    session: AsyncSession
) -> None:
    """Finalize mandatory channel addition."""
    link = message.text.strip()
    data = await state.get_data()

    channel = await SettingsService.add_mandatory_channel(
        session=session,
        channel_id=data["ch_id"],
        channel_name=data["ch_name"],
        invite_link=link,
    )

    await state.clear()
    await message.answer(
        f"✅ <b>کانال {channel.channel_name} ({channel.channel_id}) با موفقیت به لیست عضویت اجباری اضافه شد.</b>",
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("adm_channel_view:"))
async def handle_adm_channel_view(query: CallbackQuery, session: AsyncSession) -> None:
    """Delete a mandatory channel."""
    channel_id = int(query.data.split(":")[1])
    await SettingsService.delete_mandatory_channel(session, channel_id)
    await query.answer("🗑 کانال با موفقیت حذف گردید.", show_alert=True)
    channels = await SettingsService.get_mandatory_channels(session, active_only=False)
    await query.message.edit_text(
        "📢 کانال حذف شد. لیست کانال‌ها:",
        reply_markup=get_admin_channels_keyboard(channels)
    )


@router.callback_query(F.data == "adm_set_card")
async def handle_adm_set_card(query: CallbackQuery, state: FSMContext) -> None:
    """Prompt for new card number."""
    await state.update_data(setting_key="card_number")
    await state.set_state(AdminSettingsStates.edit_value)
    await query.message.answer(
        "💳 لطفاً <b>شماره کارت ۱۶ رقمی جدید</b> را وارد نمایید:",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()
    )
    await query.answer()


@router.callback_query(F.data == "adm_set_welcome")
async def handle_adm_set_welcome(query: CallbackQuery, state: FSMContext) -> None:
    """Prompt for new welcome message text."""
    await state.update_data(setting_key="welcome_message")
    await state.set_state(AdminSettingsStates.edit_value)
    await query.message.answer(
        "📝 لطفاً <b>متن خوش‌آمدگویی جدید ربات</b> را ارسال فرمایید:",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()
    )
    await query.answer()


@router.callback_query(F.data == "adm_set_hold_time")
async def handle_adm_set_hold_time(query: CallbackQuery, state: FSMContext) -> None:
    """Prompt for new reservation hold time in minutes."""
    await state.update_data(setting_key="reservation_hold_minutes")
    await state.set_state(AdminSettingsStates.edit_value)
    await query.message.answer(
        "⏱ لطفاً <b>مدت زمان رزرو موقت بر حسب دقیقه</b> را وارد فرمایید (مثال: 15):",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()
    )
    await query.answer()


@router.message(AdminSettingsStates.edit_value)
async def handle_save_setting_value(
    message: Message,
    state: FSMContext,
    session: AsyncSession
) -> None:
    """Save updated setting value."""
    val = message.text.strip()
    data = await state.get_data()
    key = data.get("setting_key")

    await SettingsService.set_setting(session, key=key, value=val)
    await state.clear()

    await message.answer(f"✅ تنظیم <code>{key}</code> با موفقیت به‌روزرسانی شد.", parse_mode="HTML")


@router.callback_query(F.data == "adm_export_excel")
async def handle_adm_export_excel(query: CallbackQuery, session: AsyncSession) -> None:
    """Generate and send Excel spreadsheet of all orders."""
    is_admin = await UserService.is_admin(session, query.from_user.id)
    if not is_admin:
        await query.answer("دسترسی غیرمجاز.", show_alert=True)
        return

    await query.answer("⏳ در حال تولید گزارش اکسل...", show_alert=False)

    stmt = select(Order).options(
        selectinload(Order.user),
        selectinload(Order.rack),
        selectinload(Order.plan)
    ).order_by(Order.created_at.desc())
    orders = (await session.execute(stmt)).scalars().all()

    wb = Workbook()
    ws = wb.active
    ws.title = "Orders"

    # Header row
    headers = [
        "ردیف", "کد سفارش", "شناسه کاربر", "نام کاربر", "نام رک",
        "تگ کلن", "پلن", "مدت (ساعت)", "مبلغ خام", "تخفیف", "مبلغ نهایی",
        "روش پرداخت", "وضعیت", "تگ پلیر", "نام اکانت", "تاریخ ثبت", "تاریخ شروع", "تاریخ پایان"
    ]
    ws.append(headers)

    for idx, ord_obj in enumerate(orders, 1):
        ws.append([
            idx,
            ord_obj.order_code,
            ord_obj.user_id,
            ord_obj.user.full_name if ord_obj.user else "",
            ord_obj.rack.name if ord_obj.rack else "",
            ord_obj.rack.clan_tag if ord_obj.rack else "",
            ord_obj.plan.title if ord_obj.plan else "",
            ord_obj.plan.duration_hours if ord_obj.plan else "",
            ord_obj.original_price,
            ord_obj.discount_amount,
            ord_obj.final_price,
            ord_obj.payment_method.value,
            ord_obj.status.value,
            ord_obj.player_tag or "",
            ord_obj.player_name or "",
            str(ord_obj.created_at),
            str(ord_obj.start_date or ""),
            str(ord_obj.end_date or ""),
        ])

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    document = BufferedInputFile(output.read(), filename="clash_rack_orders.xlsx")
    await query.message.answer_document(
        document=document,
        caption="📊 <b>گزارش اکسل کلیه سفارش‌های ثبت‌شده در سامانه</b>",
        parse_mode="HTML"
    )
