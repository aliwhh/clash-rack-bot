"""Rack browsing and tariff display handlers."""

import logging
from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import RackStatus
from bot.keyboards.inline_user import get_rack_details_keyboard, get_racks_keyboard
from bot.keyboards.reply import MAIN_MENU_TEXTS
from bot.services.rack_service import RackService
from bot.utils.formatters import format_price

logger = logging.getLogger(__name__)

router = Router(name="racks_router")


@router.message(F.text.in_([MAIN_MENU_TEXTS["rent"], MAIN_MENU_TEXTS["tariffs"]]))
async def handle_browse_racks(message: Message, session: AsyncSession) -> None:
    """Display available racks and tariffs."""
    racks = await RackService.list_active_racks(session)
    if not racks:
        await message.answer(
            "⚠️ در حال حاضر رک فعالی در سامانه ثبت نشده است.\nلطفاً بعداً مراجعه کنید یا با پشتیبانی تماس بگیرید."
        )
        return

    text = (
        "⚡️ <b>لیست رک‌ها و سرویس‌های کلش آف کلنز</b>\n\n"
        "برای مشاهده مشخصات کامل، لول کلن، نیروهای فعال و تعرفه‌های زمانی هر رک، روی نام آن کلیک نمایید:"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=get_racks_keyboard(racks))


@router.callback_query(F.data == "view_all_racks")
async def handle_view_all_racks_callback(query: CallbackQuery, session: AsyncSession) -> None:
    """Return to racks listing."""
    racks = await RackService.list_active_racks(session)
    text = (
        "⚡️ <b>لیست رک‌ها و سرویس‌های کلش آف کلنز</b>\n\n"
        "برای مشاهده مشخصات و تعرفه‌ها یکی از رک‌های زیر را انتخاب کنید:"
    )
    try:
        await query.message.edit_text(text, parse_mode="HTML", reply_markup=get_racks_keyboard(racks))
    except Exception:
        await query.message.answer(text, parse_mode="HTML", reply_markup=get_racks_keyboard(racks))
    await query.answer()


@router.callback_query(F.data.startswith("rack_view:"))
async def handle_rack_details_callback(query: CallbackQuery, session: AsyncSession) -> None:
    """Show detailed view of a selected rack."""
    rack_id = int(query.data.split(":")[1])
    rack = await RackService.get_rack_by_id(session, rack_id, load_plans=True)
    if not rack:
        await query.answer("❌ این رک یافت نشد.", show_alert=True)
        return

    status_str = {
        RackStatus.AVAILABLE: "🟢 آماده اجاره فوری",
        RackStatus.RESERVED: "🟡 در حال رزرو موقت",
        RackStatus.RENTED: "🔴 در حال استفاده (اجاره داده شده)",
        RackStatus.INACTIVE: "⚪️ غیرفعال",
    }.get(rack.status, rack.status.value)

    caption = (
        f"⚡️ <b>{rack.name}</b>\n"
        f"🏷 شناسه رک: <code>{rack.code}</code>\n"
        f"🛡 تگ کلن: <code>{rack.clan_tag or 'ثبت نشده'}</code>\n"
        f"📊 وضعیت کنونی: <b>{status_str}</b>\n\n"
        f"📝 <b>مشخصات و توضیحات:</b>\n{rack.description}\n\n"
        f"💰 <b>تعرفه‌ها و پلن‌های زمانی:</b>\n"
    )

    if rack.plans:
        for p in rack.plans:
            if p.is_active:
                discount_info = f" (تخفیف {p.discount_percent}٪)" if p.discount_percent > 0 else ""
                caption += f"▫️ {p.title} ({p.duration_hours} ساعت): <b>{format_price(p.final_price)}</b>{discount_info}\n"
    else:
        caption += "<i>تعرفه‌ای برای این رک تعریف نشده است.</i>\n"

    markup = get_rack_details_keyboard(rack, rack.plans)

    if rack.photo_file_id:
        try:
            await query.message.delete()
            await query.message.answer_photo(
                photo=rack.photo_file_id,
                caption=caption,
                parse_mode="HTML",
                reply_markup=markup
            )
            await query.answer()
            return
        except Exception as exc:
            logger.warning("Failed to display rack photo, falling back to text: %s", exc)

    try:
        await query.message.edit_text(caption, parse_mode="HTML", reply_markup=markup)
    except Exception:
        await query.message.answer(caption, parse_mode="HTML", reply_markup=markup)

    await query.answer()
