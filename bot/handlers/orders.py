"""Order creation, checkout, payment processing, and receipt submission handlers."""

import logging
from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.database.models import OrderStatus, PaymentMethod, RackStatus, User
from bot.keyboards.inline_user import (
    get_order_details_keyboard,
    get_order_summary_keyboard,
    get_payment_methods_keyboard,
    get_racks_keyboard,
)
from bot.keyboards.reply import MAIN_MENU_TEXTS, get_cancel_keyboard, get_main_menu_keyboard
from bot.services.discount_service import DiscountService
from bot.services.notification_service import NotificationService
from bot.services.order_service import OrderService
from bot.services.payment_service import PaymentService
from bot.services.rack_service import RackService
from bot.services.settings_service import SettingsService
from bot.services.user_service import UserService
from bot.states.user_states import OrderStates
from bot.utils.formatters import format_datetime, format_duration, format_price

logger = logging.getLogger(__name__)

router = Router(name="orders_router")


@router.message(F.text == MAIN_MENU_TEXTS["order"])
async def handle_start_order_text(message: Message, session: AsyncSession) -> None:
    """Entry point from reply keyboard: choose rack to start booking."""
    racks = await RackService.list_active_racks(session)
    available_racks = [r for r in racks if r.status == RackStatus.AVAILABLE]

    if not available_racks:
        await message.answer(
            "⚠️ در حال حاضر هیچ رکی با وضعیت «آماده اجاره فوری» در سیستم موجود نیست.\n"
            "می‌توانید با پشتیبانی جهت رزرو نوبت تماس بگیرید."
        )
        return

    text = (
        "📅 <b>رزرو و ثبت سفارش اجاره رک کلش</b>\n\n"
        "لطفاً رکی که مایل به اجاره آن هستید را انتخاب نمایید:"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=get_racks_keyboard(available_racks))


@router.callback_query(F.data.startswith("book_plan:"))
async def handle_book_plan_callback(
    query: CallbackQuery,
    state: FSMContext,
    session: AsyncSession
) -> None:
    """User clicked to book a specific rental plan."""
    plan_id = int(query.data.split(":")[1])
    plan = await RackService.get_plan_by_id(session, plan_id)

    if not plan or not plan.is_active or not plan.rack:
        await query.answer("❌ این پلن در حال حاضر در دسترس نیست.", show_alert=True)
        return

    # Check capacity & create temporary reservation
    reservation, msg = await OrderService.create_temporary_reservation(
        session=session,
        user_id=query.from_user.id,
        rack_id=plan.rack_id,
        plan_id=plan.id,
        hold_minutes=settings.reservation_hold_minutes
    )

    if not reservation:
        await query.answer(msg, show_alert=True)
        return

    await state.update_data(
        rack_id=plan.rack_id,
        plan_id=plan.id,
        reservation_id=reservation.id,
        plan_title=plan.title,
        duration_hours=plan.duration_hours,
        base_price=plan.final_price,
        rack_name=plan.rack.name,
    )
    await state.set_state(OrderStates.entering_player_tag)

    text = (
        f"⚡️ شما در حال رزرو <b>{plan.rack.name}</b>\n"
        f"⏱ پلن: <b>{plan.title}</b> ({format_duration(plan.duration_hours)})\n"
        f"💰 مبلغ پلن: <b>{format_price(plan.final_price)}</b>\n\n"
        f"⏳ <i>این رک به مدت {settings.reservation_hold_minutes} دقیقه برای شما رزرو موقت شد.</i>\n\n"
        f"🏷 لطفاً <b>تگ اکانت بازی خود در کلش آف کلنز</b> را ارسال فرمایید (مثال: #9V8PQL20):"
    )

    try:
        await query.message.delete()
    except Exception:
        pass

    await query.message.answer(text, parse_mode="HTML", reply_markup=get_cancel_keyboard())
    await query.answer()


@router.message(OrderStates.entering_player_tag)
async def handle_player_tag_input(message: Message, state: FSMContext) -> None:
    """Save player tag and ask for player in-game name."""
    tag = message.text.strip().upper()
    if not tag.startswith("#"):
        tag = f"#{tag}"

    await state.update_data(player_tag=tag)
    await state.set_state(OrderStates.entering_player_name)

    await message.answer(
        f"✅ تگ پلیر شما: <code>{tag}</code>\n\n"
        f"👤 لطفاً <b>نام نمایشی اکانت بازی خود</b> در کلش را ارسال فرمایید:",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()
    )


@router.message(OrderStates.entering_player_name)
async def handle_player_name_input(message: Message, state: FSMContext) -> None:
    """Save player name and ask for optional notes."""
    name = message.text.strip()
    await state.update_data(player_name=name)
    await state.set_state(OrderStates.entering_notes)

    await message.answer(
        f"✅ نام اکانت ثبت شد: <b>{name}</b>\n\n"
        f"📝 در صورتی که <b>توضیحات یا درخواست خاصی</b> (مثلاً نیروهای دونیت مدنظر) دارید ارسال کنید، "
        f"یا کلمه «<b>ندارم</b>» را بفرستید:",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()
    )


@router.message(OrderStates.entering_notes)
async def handle_notes_input(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot
) -> None:
    """Create order record and present order summary for payment."""
    raw_notes = message.text.strip()
    notes = None if raw_notes in ["ندارم", "خیر", "ندارد", "-"] else raw_notes

    data = await state.get_data()
    rack_id = data.get("rack_id")
    plan_id = data.get("plan_id")
    reservation_id = data.get("reservation_id")
    player_tag = data.get("player_tag")
    player_name = data.get("player_name")

    # Create formal order in database
    order = await OrderService.create_order(
        session=session,
        user_id=message.from_user.id,
        rack_id=rack_id,
        plan_id=plan_id,
        payment_method=PaymentMethod.ONLINE,
        player_tag=player_tag,
        player_name=player_name,
        notes=notes,
        reservation_id=reservation_id,
    )

    # Notify admins about newly registered order
    await NotificationService.notify_order_created(bot, order)

    await state.clear()
    is_admin = await UserService.is_admin(session, message.from_user.id)

    summary_text = (
        f"🧾 <b>خلاصه پیش‌فاکتور سفارش اجاره رک</b>\n\n"
        f"▫️ کد رهگیری سفارش: <code>{order.order_code}</code>\n"
        f"▫️ رک انتخابی: <b>{order.rack.name}</b>\n"
        f"▫️ تگ کلن: <code>{order.rack.clan_tag or 'ثبت نشده'}</code>\n"
        f"▫️ پلن زمانی: <b>{order.plan.title}</b> ({format_duration(order.plan.duration_hours)})\n"
        f"▫️ تگ اکانت شما: <code>{order.player_tag}</code>\n"
        f"▫️ نام اکانت شما: <b>{order.player_name}</b>\n"
        f"▫️ مبلغ پایه: {format_price(order.original_price)}\n"
        f"▫️ تخفیف: {format_price(order.discount_amount)}\n"
        f"💳 <b>مبلغ قابل پرداخت: {format_price(order.final_price)}</b>\n\n"
        f"⏳ <i>مهلت تکمیل پرداخت: {settings.reservation_hold_minutes} دقیقه</i>"
    )

    await message.answer(
        "سفارش شما با موفقیت ایجاد گردید.",
        reply_markup=get_main_menu_keyboard(is_admin=is_admin)
    )
    await message.answer(
        summary_text,
        parse_mode="HTML",
        reply_markup=get_order_summary_keyboard(order.id, has_discount=order.discount_amount > 0)
    )


@router.callback_query(F.data.startswith("apply_discount:"))
async def handle_apply_discount_callback(
    query: CallbackQuery,
    state: FSMContext
) -> None:
    """Prompt user to enter promo discount code."""
    order_id = int(query.data.split(":")[1])
    await state.update_data(discount_order_id=order_id)
    await state.set_state(OrderStates.applying_discount)

    await query.message.answer(
        "🎟 لطفاً <b>کد تخفیف</b> خود را ارسال نمایید:",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()
    )
    await query.answer()


@router.message(OrderStates.applying_discount)
async def handle_discount_code_input(
    message: Message,
    state: FSMContext,
    session: AsyncSession
) -> None:
    """Validate and apply discount code to the order."""
    code_text = message.text.strip().upper()
    data = await state.get_data()
    order_id = data.get("discount_order_id")

    order = await OrderService.get_order_by_id(session, order_id)
    if not order or order.status != OrderStatus.PENDING_PAYMENT:
        await state.clear()
        await message.answer("❌ سفارش منقضی یا نامعتبر است.")
        return

    is_valid, msg, discount_val, discount_obj = await DiscountService.validate_discount(
        session=session,
        code=code_text,
        user_id=message.from_user.id,
        order_amount=order.original_price
    )

    if not is_valid or not discount_obj:
        await message.answer(f"{msg}\nلطفاً کد دیگری وارد کنید یا «❌ انصراف و بازگشت» را بزنید:")
        return

    # Apply to order
    order.discount_code_id = discount_obj.id
    order.discount_amount = discount_val
    order.final_price = max(0, order.original_price - discount_val)
    await session.flush()
    await DiscountService.increment_usage(session, discount_obj.id)

    await state.clear()
    is_admin = await UserService.is_admin(session, message.from_user.id)

    summary_text = (
        f"✅ <b>کد تخفیف اعمال شد!</b>\n\n"
        f"▫️ کد سفارش: <code>{order.order_code}</code>\n"
        f"▫️ مبلغ اولیه: {format_price(order.original_price)}\n"
        f"▫️ میزان تخفیف: <b>{format_price(order.discount_amount)}</b>\n"
        f"💳 <b>مبلغ نهایی جدید: {format_price(order.final_price)}</b>\n"
    )

    await message.answer(summary_text, parse_mode="HTML", reply_markup=get_main_menu_keyboard(is_admin=is_admin))
    await message.answer(
        "جهت تکمیل فرآیند روی رفتن به مرحله پرداخت کلیک کنید:",
        reply_markup=get_order_summary_keyboard(order.id, has_discount=True)
    )


@router.callback_query(F.data.startswith("proceed_pay:"))
async def handle_proceed_pay_callback(
    query: CallbackQuery,
    session: AsyncSession
) -> None:
    """Show available payment options (Online or Card-to-Card)."""
    order_id = int(query.data.split(":")[1])
    order = await OrderService.get_order_by_id(session, order_id)

    if not order:
        await query.answer("❌ سفارش یافت نشد.", show_alert=True)
        return

    if order.status != OrderStatus.PENDING_PAYMENT:
        await query.answer("⚠️ این سفارش دیگر در انتظار پرداخت نمی‌باشد.", show_alert=True)
        return

    # Request online payment link
    success, msg, pay_url, _ = await PaymentService.request_online_payment(
        session=session,
        order=order
    )

    pay_text = (
        f"💳 <b>انتخاب روش پرداخت</b>\n\n"
        f"▫️ کد سفارش: <code>{order.order_code}</code>\n"
        f"▫️ مبلغ قابل پرداخت: <b>{format_price(order.final_price)}</b>\n\n"
        f"یکی از روش‌های زیر را جهت پرداخت انتخاب فرمایید:"
    )

    markup = get_payment_methods_keyboard(order.id, online_url=pay_url if success else None)

    try:
        await query.message.edit_text(pay_text, parse_mode="HTML", reply_markup=markup)
    except Exception:
        await query.message.answer(pay_text, parse_mode="HTML", reply_markup=markup)

    await query.answer()


@router.callback_query(F.data.startswith("verify_online:"))
async def handle_verify_online_callback(
    query: CallbackQuery,
    session: AsyncSession,
    bot: Bot
) -> None:
    """Verify online transaction result."""
    order_id = int(query.data.split(":")[1])
    order = await OrderService.get_order_by_id(session, order_id)

    if not order or not order.payments:
        await query.answer("❌ اطلاعات پرداخت یافت نشد.", show_alert=True)
        return

    # Find latest pending online payment
    online_payments = [p for p in order.payments if p.payment_method == PaymentMethod.ONLINE]
    if not online_payments:
        await query.answer("❌ تراکنش آنلاینی برای این سفارش ثبت نشده است.", show_alert=True)
        return

    latest_pay = online_payments[-1]
    verified, v_msg, _ = await PaymentService.verify_online_payment(
        session=session,
        authority=latest_pay.authority,
        amount=order.final_price
    )

    if verified:
        await query.answer(v_msg, show_alert=True)
        # Notify user with approval card
        await NotificationService.notify_order_approved(bot, order)
        try:
            await query.message.edit_text(
                f"🎉 <b>پرداخت شما با موفقیت تأیید شد!</b>\n\n"
                f"سفارش <code>{order.order_code}</code> فعال گردید.\n"
                f"جهت مشاهده اطلاعات بیشتر به بخش «سفارش‌های من» مراجعه فرمایید.",
                parse_mode="HTML"
            )
        except Exception:
            pass
    else:
        await query.answer(v_msg, show_alert=True)


@router.callback_query(F.data.startswith("pay_c2c:"))
async def handle_pay_c2c_callback(
    query: CallbackQuery,
    state: FSMContext,
    session: AsyncSession
) -> None:
    """Display bank card info and enter receipt photo upload state."""
    order_id = int(query.data.split(":")[1])
    order = await OrderService.get_order_by_id(session, order_id)

    if not order or order.status != OrderStatus.PENDING_PAYMENT:
        await query.answer("❌ این سفارش در انتظار پرداخت نمی‌باشد.", show_alert=True)
        return

    card_num = await SettingsService.get_setting(session, "card_number", default=settings.card_number)
    card_holder = await SettingsService.get_setting(session, "card_holder_name", default=settings.card_holder_name)
    bank_name = await SettingsService.get_setting(session, "bank_name", default=settings.bank_name)

    await state.update_data(c2c_order_id=order_id)
    await state.set_state(OrderStates.uploading_receipt_photo)

    c2c_text = (
        f"💳 <b>پرداخت به روش کارت به کارت</b>\n\n"
        f"▫️ مبلغ قابل واریز: <b>{format_price(order.final_price)}</b>\n"
        f"▫️ شماره کارت: <code>{card_num}</code>\n"
        f"▫️ به نام: <b>{card_holder}</b>\n"
        f"▫️ بانک: <b>{bank_name}</b>\n\n"
        f"⚠️ لطفاً پس از واریز، <b>عکس یا اسکرین‌شات واضح فیش واریزی</b> را در همین صفحه ارسال فرمایید:"
    )

    await query.message.answer(c2c_text, parse_mode="HTML", reply_markup=get_cancel_keyboard())
    await query.answer()


@router.message(OrderStates.uploading_receipt_photo, F.photo)
async def handle_receipt_photo_input(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot
) -> None:
    """Receive receipt photo and ask for sender's card number (optional/recommended)."""
    photo = message.photo[-1]  # Highest resolution photo
    data = await state.get_data()
    order_id = data.get("c2c_order_id")

    await state.update_data(receipt_photo_id=photo.file_id)
    await state.set_state(OrderStates.entering_sender_card)

    await message.answer(
        "✅ فیش واریزی با موفقیت دریافت شد.\n\n"
        "💳 جهت تسریع در فرآیند بررسی، لطفاً <b>۴ رقم آخر شماره کارت واریزکننده</b> را ارسال نمایید "
        "(یا در صورت عدم تمایل کلمه «<b>ارسال شد</b>» را بفرستید):",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()
    )


@router.message(OrderStates.entering_sender_card)
async def handle_sender_card_input(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot
) -> None:
    """Finalize Card-to-Card receipt submission and notify admins."""
    card_info = message.text.strip()
    data = await state.get_data()
    order_id = data.get("c2c_order_id")
    receipt_photo_id = data.get("receipt_photo_id")

    success, msg, payment = await PaymentService.submit_card_to_card_receipt(
        session=session,
        order_id=order_id,
        user_id=message.from_user.id,
        receipt_photo_id=receipt_photo_id,
        card_number=card_info if card_info not in ["ارسال شد", "ندارم"] else None
    )

    if not success or not payment:
        await message.answer(msg)
        return

    order = await OrderService.get_order_by_id(session, order_id)
    await NotificationService.notify_card_to_card_pending(bot, order, payment)

    await state.clear()
    is_admin = await UserService.is_admin(session, message.from_user.id)

    response_text = (
        f"✅ <b>رسید پرداخت شما با موفقیت ثبت شد!</b>\n\n"
        f"▫️ کد سفارش: <code>{order.order_code}</code>\n"
        f"▫️ وضعیت: <b>در انتظار تأیید مدیریت</b> ⏳\n\n"
        f"تیم پشتیبانی و مدیریت در اسرع وقت فیش واریزی شما را بررسی و سرویس را فعال خواهند نمود.\n"
        f"نتیجه بررسی از طریق همین ربات به شما اطلاع‌رسانی خواهد شد."
    )

    await message.answer(response_text, parse_mode="HTML", reply_markup=get_main_menu_keyboard(is_admin=is_admin))


@router.callback_query(F.data.startswith("cancel_order_user:"))
async def handle_cancel_order_user_callback(
    query: CallbackQuery,
    session: AsyncSession
) -> None:
    """User willingly cancels pending order."""
    order_id = int(query.data.split(":")[1])
    success, msg, _ = await OrderService.cancel_order(
        session=session,
        order_id=order_id,
        reason="لغو شده توسط کاربر"
    )

    await query.answer(msg, show_alert=True)
    try:
        await query.message.edit_text(
            f"❌ سفارش با موفقیت لغو گردید و ظرفیت رک آزاد شد.",
            parse_mode="HTML"
        )
    except Exception:
        pass


@router.callback_query(F.data.startswith("view_order:"))
async def handle_view_order_callback(query: CallbackQuery, session: AsyncSession) -> None:
    """View full details of an order."""
    order_id = int(query.data.split(":")[1])
    order = await OrderService.get_order_by_id(session, order_id)

    if not order:
        await query.answer("❌ سفارش یافت نشد.", show_alert=True)
        return

    status_persian = {
        OrderStatus.PENDING_PAYMENT: "⏳ در انتظار پرداخت",
        OrderStatus.PENDING_APPROVAL: "🔍 در حال بررسی فیش واریزی",
        OrderStatus.ACTIVE: "🟢 فعال و در حال استفاده",
        OrderStatus.COMPLETED: "✅ پایان یافته",
        OrderStatus.CANCELLED: "❌ لغو شده",
        OrderStatus.EXPIRED: "⌛️ منقضی شده",
    }.get(order.status, order.status.value)

    text = (
        f"📦 <b>جزئیات سفارش {order.order_code}</b>\n\n"
        f"▫️ سرویس: <b>{order.rack.name}</b>\n"
        f"▫️ تگ کلن: <code>{order.rack.clan_tag or 'ثبت نشده'}</code>\n"
        f"▫️ پلن: <b>{order.plan.title}</b> ({format_duration(order.plan.duration_hours)})\n"
        f"▫️ تگ پلیر: <code>{order.player_tag or 'ندارد'}</code>\n"
        f"▫️ نام اکانت: <b>{order.player_name or 'ندارد'}</b>\n"
        f"▫️ وضعیت سفارش: <b>{status_persian}</b>\n"
        f"▫️ روش پرداخت: {order.payment_method.value}\n"
        f"▫️ مبلغ پرداختی: <b>{format_price(order.final_price)}</b>\n"
        f"▫️ تاریخ ثبت: {format_datetime(order.created_at)}\n"
        f"▫️ تاریخ شروع: {format_datetime(order.start_date)}\n"
        f"▫️ تاریخ پایان: {format_datetime(order.end_date)}\n"
    )

    if order.notes:
        text += f"▫️ توضیحات شما: {order.notes}\n"

    try:
        await query.message.edit_text(text, parse_mode="HTML", reply_markup=get_order_details_keyboard(order))
    except Exception:
        await query.message.answer(text, parse_mode="HTML", reply_markup=get_order_details_keyboard(order))

    await query.answer()
