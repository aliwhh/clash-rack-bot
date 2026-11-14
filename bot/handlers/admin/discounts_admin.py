"""Admin Promotional Discount Code Handlers."""

import logging
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import DiscountType
from bot.keyboards.inline_admin import get_admin_discounts_keyboard
from bot.keyboards.reply import get_cancel_keyboard
from bot.services.discount_service import DiscountService
from bot.services.user_service import UserService
from bot.states.admin_states import AdminDiscountStates

logger = logging.getLogger(__name__)

router = Router(name="admin_discounts_router")


@router.callback_query(F.data == "adm_discounts")
async def handle_adm_discounts(query: CallbackQuery, session: AsyncSession) -> None:
    """List discount codes in admin."""
    is_admin = await UserService.is_admin(session, query.from_user.id)
    if not is_admin:
        await query.answer("دسترسی غیرمجاز.", show_alert=True)
        return

    discounts = await DiscountService.list_discounts(session)
    text = (
        "🎟 <b>مدیریت کدهای تخفیف</b>\n\n"
        "جهت مشاهده جزئیات روی کد کلیک کنید یا دکمه «➕ ایجاد کد تخفیف جدید» را بزنید:"
    )

    markup = get_admin_discounts_keyboard(discounts)
    try:
        await query.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    except Exception:
        await query.message.answer(text, parse_mode="HTML", reply_markup=markup)
    await query.answer()


@router.callback_query(F.data == "adm_discount_add")
async def handle_adm_discount_add(query: CallbackQuery, state: FSMContext) -> None:
    """Prompt for discount code text."""
    await state.set_state(AdminDiscountStates.code)
    await query.message.answer(
        "➕ <b>تعریف کد تخفیف جدید</b>\n\n"
        "لطفاً <b>کد انگلیسی تخفیف</b> را وارد کنید (مثال: CLASH2026):",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()
    )
    await query.answer()


@router.message(AdminDiscountStates.code)
async def handle_discount_code_input(message: Message, state: FSMContext) -> None:
    """Store code and ask for type (percent or fixed)."""
    code = message.text.strip().upper()
    await state.update_data(code=code)
    await state.set_state(AdminDiscountStates.discount_type)

    await message.answer(
        "نوع تخفیف چیست؟\n"
        "برای تخفیف درصدی عدد <b>1</b> و برای مبلغ ثابت به تومان عدد <b>2</b> را بفرستید:",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()
    )


@router.message(AdminDiscountStates.discount_type)
async def handle_discount_type_input(message: Message, state: FSMContext) -> None:
    """Store type and ask for value."""
    text = message.text.strip()
    dtype = DiscountType.PERCENT if text == "1" else DiscountType.FIXED
    await state.update_data(discount_type=dtype)
    await state.set_state(AdminDiscountStates.value)

    prompt = "درصد تخفیف را وارد کنید (مثال: 20):" if dtype == DiscountType.PERCENT else "مبلغ تخفیف به تومان را وارد کنید (مثال: 50000):"
    await message.answer(prompt, reply_markup=get_cancel_keyboard())


@router.message(AdminDiscountStates.value)
async def handle_discount_value_input(message: Message, state: FSMContext) -> None:
    """Store value and ask for usage limit."""
    text = message.text.strip()
    if not text.isdigit() or int(text) <= 0:
        await message.answer("❌ لطفاً یک عدد معتبر وارد کنید:")
        return

    await state.update_data(value=int(text))
    await state.set_state(AdminDiscountStates.usage_limit)

    await message.answer(
        "🔢 <b>سقف تعداد کل استفاده</b> از این کد چند بار باشد؟ "
        "(مثال: 100، یا در صورت نامحدود بودن عدد 0 را وارد فرمایید):",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()
    )


@router.message(AdminDiscountStates.usage_limit)
async def handle_discount_limit_input(
    message: Message,
    state: FSMContext,
    session: AsyncSession
) -> None:
    """Finalize discount creation."""
    text = message.text.strip()
    limit = int(text) if text.isdigit() and int(text) > 0 else None

    data = await state.get_data()
    discount = await DiscountService.create_discount(
        session=session,
        code=data["code"],
        discount_type=data["discount_type"],
        value=data["value"],
        usage_limit=limit,
    )

    await state.clear()
    await message.answer(
        f"✅ <b>کد تخفیف <code>{discount.code}</code> با موفقیت ایجاد شد!</b>\n"
        f"▫️ نوع: {discount.discount_type.value}\n"
        f"▫️ مقدار: {discount.value}\n"
        f"▫️ سقف استفاده: {discount.usage_limit or 'نامحدود'}",
        parse_mode="HTML"
    )
