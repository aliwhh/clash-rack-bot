"""Admin Rack and Rental Plan Management Handlers."""

import logging
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import RackStatus
from bot.keyboards.inline_admin import get_admin_rack_actions_keyboard, get_admin_racks_keyboard
from bot.keyboards.reply import get_cancel_keyboard
from bot.services.rack_service import RackService
from bot.services.user_service import UserService
from bot.states.admin_states import AdminPlanStates, AdminRackStates
from bot.utils.formatters import format_price

logger = logging.getLogger(__name__)

router = Router(name="admin_racks_router")


@router.callback_query(F.data == "adm_racks")
async def handle_adm_racks(query: CallbackQuery, session: AsyncSession) -> None:
    """List all racks for admin management."""
    is_admin = await UserService.is_admin(session, query.from_user.id)
    if not is_admin:
        await query.answer("دسترسی غیرمجاز.", show_alert=True)
        return

    racks = await RackService.list_all_racks_admin(session)
    text = (
        "⚡️ <b>مدیریت رک‌ها و سرویس‌های کلش</b>\n\n"
        "جهت مشاهده، ویرایش، افزودن پلن، یا غیرفعال‌سازی روی رک مورد نظر کلیک کنید "
        "یا دکمه «➕ افزودن رک جدید» را بزنید:"
    )
    try:
        await query.message.edit_text(text, parse_mode="HTML", reply_markup=get_admin_racks_keyboard(racks))
    except Exception:
        await query.message.answer(text, parse_mode="HTML", reply_markup=get_admin_racks_keyboard(racks))
    await query.answer()


@router.callback_query(F.data == "adm_rack_add")
async def handle_adm_rack_add(query: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    """Begin rack creation wizard."""
    is_admin = await UserService.is_admin(session, query.from_user.id)
    if not is_admin:
        await query.answer("دسترسی غیرمجاز.", show_alert=True)
        return

    await state.set_state(AdminRackStates.name)
    await query.message.answer(
        "➕ <b>افزودن رک جدید (مرحله ۱ از ۶)</b>\n\n"
        "لطفاً <b>نام رک</b> را وارد فرمایید (مثال: رک لول ۲۶ سوپر دراگ و الکترو):",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()
    )
    await query.answer()


@router.message(AdminRackStates.name)
async def handle_rack_name_input(message: Message, state: FSMContext) -> None:
    """Store name and ask for code."""
    await state.update_data(name=message.text.strip())
    await state.set_state(AdminRackStates.code)
    await message.answer(
        "🏷 <b>(مرحله ۲ از ۶):</b> لطفاً <b>شناسه انگلیسی رک</b> را وارد کنید (مثال: RACK-202):",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()
    )


@router.message(AdminRackStates.code)
async def handle_rack_code_input(message: Message, state: FSMContext, session: AsyncSession) -> None:
    """Store code and check uniqueness."""
    code = message.text.strip().upper()
    existing = await RackService.get_rack_by_code(session, code)
    if existing:
        await message.answer("❌ این شناسه رک قبلاً ثبت شده است. لطفاً شناسه دیگری وارد کنید:")
        return

    await state.update_data(code=code)
    await state.set_state(AdminRackStates.clan_tag)
    await message.answer(
        "🛡 <b>(مرحله ۳ از ۶):</b> لطفاً <b>تگ کلن در بازی</b> را وارد نمایید (مثال: #2Y90LVPG) "
        "یا در صورت عدم تمایل کلمه «<b>ندارد</b>» را بفرستید:",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()
    )


@router.message(AdminRackStates.clan_tag)
async def handle_rack_clan_tag_input(message: Message, state: FSMContext) -> None:
    """Store clan tag and ask for description."""
    tag = message.text.strip().upper()
    clan_tag = None if tag in ["ندارد", "خیر", "-"] else tag
    await state.update_data(clan_tag=clan_tag)
    await state.set_state(AdminRackStates.description)

    await message.answer(
        "📝 <b>(مرحله ۴ از ۶):</b> لطفاً <b>مشخصات و توضیحات کامل رک</b> را ارسال کنید "
        "(لول کلن، نیروهای باز، قوانین دونیت و ...):",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()
    )


@router.message(AdminRackStates.description)
async def handle_rack_description_input(message: Message, state: FSMContext) -> None:
    """Store description and ask for capacity."""
    await state.update_data(description=message.text.strip())
    await state.set_state(AdminRackStates.capacity)

    await message.answer(
        "👥 <b>(مرحله ۵ از ۶):</b> <b>ظرفیت پذیرش همزمان</b> این رک چند نفر است؟ (معمولاً عدد 1):",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()
    )


@router.message(AdminRackStates.capacity)
async def handle_rack_capacity_input(message: Message, state: FSMContext) -> None:
    """Store capacity and ask for photo."""
    text = message.text.strip()
    capacity = int(text) if text.isdigit() and int(text) > 0 else 1
    await state.update_data(capacity=capacity)
    await state.set_state(AdminRackStates.photo)

    await message.answer(
        "🖼 <b>(مرحله ۶ از ۶):</b> لطفاً <b>تصویر رک/کلن</b> را ارسال نمایید "
        "(یا در صورت عدم نیاز به عکس، کلمه «<b>بدون عکس</b>» را بفرستید):",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()
    )


@router.message(AdminRackStates.photo)
async def handle_rack_photo_input(
    message: Message,
    state: FSMContext,
    session: AsyncSession
) -> None:
    """Finalize rack creation."""
    photo_file_id = message.photo[-1].file_id if message.photo else None
    data = await state.get_data()

    rack = await RackService.create_rack(
        session=session,
        name=data["name"],
        code=data["code"],
        clan_tag=data.get("clan_tag"),
        description=data["description"],
        capacity=data.get("capacity", 1),
        photo_file_id=photo_file_id,
    )

    await state.clear()
    await message.answer(
        f"✅ <b>رک جدید با موفقیت ایجاد شد!</b>\n\n"
        f"▫️ نام رک: <b>{rack.name}</b>\n"
        f"▫️ شناسه: <code>{rack.code}</code>\n"
        f"▫️ تگ کلن: <code>{rack.clan_tag or 'ندارد'}</code>\n\n"
        f"⚠️ هم‌اکنون می‌توانید از پنل رک برای آن <b>پلن‌های زمانی</b> (۱ روزه، هفتگی و ...) تعریف نمایید.",
        parse_mode="HTML",
        reply_markup=get_admin_rack_actions_keyboard(rack)
    )


@router.callback_query(F.data.startswith("adm_rack_view:"))
async def handle_adm_rack_view(query: CallbackQuery, session: AsyncSession) -> None:
    """View rack details in admin."""
    rack_id = int(query.data.split(":")[1])
    rack = await RackService.get_rack_by_id(session, rack_id, load_plans=True)
    if not rack:
        await query.answer("رک یافت نشد.", show_alert=True)
        return

    plans_text = ""
    for p in rack.plans:
        plans_text += f"▫️ {p.title} ({p.duration_hours} ساعت) - {format_price(p.final_price)}\n"

    status_tag = "🟢 فعال" if rack.is_active else "🔴 غیرفعال"

    text = (
        f"⚡️ <b>مدیریت رک: {rack.name}</b>\n\n"
        f"▫️ شناسه: <code>{rack.code}</code>\n"
        f"▫️ تگ کلن: <code>{rack.clan_tag or 'ندارد'}</code>\n"
        f"▫️ وضعیت فعلی: <b>{status_tag} ({rack.status.value})</b>\n"
        f"▫️ ظرفیت: {rack.capacity} اسلات\n\n"
        f"📝 <b>توضیحات:</b>\n{rack.description}\n\n"
        f"💰 <b>پلن‌های تعریف‌شده:</b>\n"
        f"{plans_text if plans_text else 'پلنی تعریف نشده است.\n'}"
    )

    markup = get_admin_rack_actions_keyboard(rack)
    try:
        await query.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    except Exception:
        await query.message.answer(text, parse_mode="HTML", reply_markup=markup)
    await query.answer()


@router.callback_query(F.data.startswith("adm_rack_toggle:"))
async def handle_adm_rack_toggle(query: CallbackQuery, session: AsyncSession) -> None:
    """Toggle rack active status."""
    rack_id = int(query.data.split(":")[1])
    rack = await RackService.get_rack_by_id(session, rack_id, load_plans=False)
    if rack:
        rack.is_active = not rack.is_active
        await session.flush()
        state_str = "فعال" if rack.is_active else "غیرفعال"
        await query.answer(f"رک با موفقیت {state_str} شد.", show_alert=True)
        # Refresh view
        rack_full = await RackService.get_rack_by_id(session, rack_id, load_plans=True)
        try:
            await query.message.edit_reply_markup(reply_markup=get_admin_rack_actions_keyboard(rack_full))
        except Exception:
            pass


@router.callback_query(F.data.startswith("adm_rack_delete:"))
async def handle_adm_rack_delete(query: CallbackQuery, session: AsyncSession) -> None:
    """Delete rack."""
    rack_id = int(query.data.split(":")[1])
    await RackService.delete_rack(session, rack_id)
    await query.answer("🗑 رک با موفقیت حذف گردید.", show_alert=True)
    racks = await RackService.list_all_racks_admin(session)
    await query.message.edit_text(
        "⚡️ رک حذف شد. لیست به‌روزرسانی‌شده رک‌ها:",
        reply_markup=get_admin_racks_keyboard(racks)
    )


@router.callback_query(F.data.startswith("adm_plan_add:"))
async def handle_adm_plan_add(query: CallbackQuery, state: FSMContext) -> None:
    """Begin adding rental plan to rack."""
    rack_id = int(query.data.split(":")[1])
    await state.update_data(target_rack_id=rack_id)
    await state.set_state(AdminPlanStates.title)

    await query.message.answer(
        "➕ <b>افزودن پلن زمانی به رک</b>\n\n"
        "لطفاً <b>عنوان پلن</b> را وارد فرمایید (مثال: ۱ روزه، ۳ روزه وار لیگ، هفتگی، ماهانه):",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()
    )
    await query.answer()


@router.message(AdminPlanStates.title)
async def handle_plan_title_input(message: Message, state: FSMContext) -> None:
    """Store title and ask for duration in hours."""
    await state.update_data(title=message.text.strip())
    await state.set_state(AdminPlanStates.duration_hours)
    await message.answer(
        "⏱ لطفاً <b>مدت زمان پلن را به ساعت</b> وارد فرمایید (مثال: برای ۱ روز عدد 24، برای ۳ روز 72، برای ۱ هفته 168):",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()
    )


@router.message(AdminPlanStates.duration_hours)
async def handle_plan_duration_input(message: Message, state: FSMContext) -> None:
    """Store hours and ask for price."""
    text = message.text.strip()
    if not text.isdigit() or int(text) <= 0:
        await message.answer("❌ لطفاً یک عدد صحیح معتبر برای ساعت وارد کنید:")
        return

    await state.update_data(duration_hours=int(text))
    await state.set_state(AdminPlanStates.price)
    await message.answer(
        "💰 لطفاً <b>قیمت پلن به تومان</b> را وارد کنید (مثال: 50000):",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()
    )


@router.message(AdminPlanStates.price)
async def handle_plan_price_input(message: Message, state: FSMContext) -> None:
    """Store price and ask for discount percent."""
    text = message.text.strip()
    if not text.isdigit() or int(text) < 0:
        await message.answer("❌ لطفاً یک مبلغ معتبر به عدد وارد کنید:")
        return

    await state.update_data(price=int(text))
    await state.set_state(AdminPlanStates.discount_percent)
    await message.answer(
        "🎁 <b>درصد تخفیف پیش‌فرض پلن</b> را وارد فرمایید (عدد 0 تا 100):",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()
    )


@router.message(AdminPlanStates.discount_percent)
async def handle_plan_discount_input(
    message: Message,
    state: FSMContext,
    session: AsyncSession
) -> None:
    """Finalize rental plan creation."""
    text = message.text.strip()
    discount = int(text) if text.isdigit() and 0 <= int(text) <= 100 else 0

    data = await state.get_data()
    rack_id = data["target_rack_id"]

    plan = await RackService.add_rental_plan(
        session=session,
        rack_id=rack_id,
        title=data["title"],
        duration_hours=data["duration_hours"],
        price=data["price"],
        discount_percent=discount,
    )

    rack = await RackService.get_rack_by_id(session, rack_id, load_plans=True)
    await state.clear()

    await message.answer(
        f"✅ <b>پلن {plan.title} با موفقیت به رک اضافه شد!</b>\n"
        f"▫️ مدت: {plan.duration_hours} ساعت\n"
        f"▫️ قیمت: {format_price(plan.final_price)}",
        parse_mode="HTML",
        reply_markup=get_admin_rack_actions_keyboard(rack)
    )
