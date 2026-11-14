"""Interactive Rental Cost Calculator Handlers."""

import logging
from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.inline_user import get_calculator_plans_keyboard, get_calculator_racks_keyboard
from bot.keyboards.reply import MAIN_MENU_TEXTS
from bot.services.rack_service import RackService
from bot.utils.formatters import format_duration, format_price

logger = logging.getLogger(__name__)

router = Router(name="calculator_router")


@router.message(F.text == MAIN_MENU_TEXTS["calculator"])
async def handle_calculator_start(message: Message, session: AsyncSession) -> None:
    """Initialize interactive rental cost calculator."""
    racks = await RackService.list_active_racks(session)
    if not racks:
        await message.answer("⚠️ در حال حاضر رکی برای محاسبه هزینه موجود نیست.")
        return

    text = (
        "🧮 <b>سیستم محاسبه هزینه اجاره رک کلش</b>\n\n"
        "با استفاده از این بخش می‌توانید هزینه سرویس‌های مختلف، تخفیف‌های دوره‌ای "
        "و نرخ ساعتی/روزانه هر رک را قبل از ثبت سفارش محاسبه و مقایسه کنید.\n\n"
        "ابتدا <b>رک مورد نظر</b> را انتخاب فرمایید:"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=get_calculator_racks_keyboard(racks))


@router.callback_query(F.data == "calc_start")
async def handle_calc_start_callback(query: CallbackQuery, session: AsyncSession) -> None:
    """Return to calculator initial screen."""
    racks = await RackService.list_active_racks(session)
    text = (
        "🧮 <b>محاسبه هوشمند هزینه اجاره رک</b>\n\n"
        "لطفاً رک مورد نظر را انتخاب فرمایید:"
    )
    try:
        await query.message.edit_text(text, parse_mode="HTML", reply_markup=get_calculator_racks_keyboard(racks))
    except Exception:
        await query.message.answer(text, parse_mode="HTML", reply_markup=get_calculator_racks_keyboard(racks))
    await query.answer()


@router.callback_query(F.data.startswith("calc_rack:"))
async def handle_calc_rack_selected(query: CallbackQuery, session: AsyncSession) -> None:
    """Rack selected in calculator; show available duration plans."""
    rack_id = int(query.data.split(":")[1])
    rack = await RackService.get_rack_by_id(session, rack_id, load_plans=True)

    if not rack:
        await query.answer("❌ رک یافت نشد.", show_alert=True)
        return

    text = (
        f"🧮 <b>محاسبه‌گر هزینه برای: {rack.name}</b>\n\n"
        f"اکنون <b>مدت زمان اجاره</b> را انتخاب نمایید تا جزئیات قیمت و تخفیف محاسبه گردد:"
    )

    try:
        await query.message.edit_text(text, parse_mode="HTML", reply_markup=get_calculator_plans_keyboard(rack.plans))
    except Exception:
        await query.message.answer(text, parse_mode="HTML", reply_markup=get_calculator_plans_keyboard(rack.plans))
    await query.answer()


@router.callback_query(F.data.startswith("calc_plan:"))
async def handle_calc_plan_selected(query: CallbackQuery, session: AsyncSession) -> None:
    """Calculate and output detailed cost breakdown."""
    plan_id = int(query.data.split(":")[1])
    plan = await RackService.get_plan_by_id(session, plan_id)

    if not plan:
        await query.answer("❌ پلن یافت نشد.", show_alert=True)
        return

    hourly_rate = plan.final_price / plan.duration_hours
    daily_rate = hourly_rate * 24

    savings_text = ""
    if plan.discount_percent > 0:
        saved_amount = int(plan.price * (plan.discount_percent / 100))
        savings_text = (
            f"🎁 <b>میزان تخفیف دوره:</b> {plan.discount_percent}٪ ({format_price(saved_amount)})\n"
            f"▫️ مبلغ خام قبل از تخفیف: <s>{format_price(plan.price)}</s>\n"
        )

    text = (
        f"🧮 <b>نتیجه محاسبه هزینه اجاره:</b>\n\n"
        f"▫️ رک: <b>{plan.rack.name}</b>\n"
        f"▫️ پلن زمانی: <b>{plan.title}</b> ({format_duration(plan.duration_hours)})\n"
        f"{savings_text}"
        f"💳 <b>مبلغ نهایی پلن: {format_price(plan.final_price)}</b>\n\n"
        f"📊 <b>آنالیز نرخ زمانی:</b>\n"
        f"▫️ نرخ به ازای هر ساعت: ~{format_price(int(hourly_rate))}\n"
        f"▫️ نرخ معادل شبانه‌روز (۲۴ساعته): ~{format_price(int(daily_rate))}\n\n"
        f"⚡️ جهت رزرو این پلن روی دکمه زیر کلیک کنید:"
    )

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⚡️ رزرو و خرید همین پلن", callback_data=f"book_plan:{plan.id}")
        ],
        [
            InlineKeyboardButton(text="🔄 محاسبه پلن دیگر", callback_data=f"calc_rack:{plan.rack_id}"),
            InlineKeyboardButton(text="🔙 بازگشت به رک‌ها", callback_data="calc_start"),
        ]
    ])

    try:
        await query.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    except Exception:
        await query.message.answer(text, parse_mode="HTML", reply_markup=markup)
    await query.answer()
