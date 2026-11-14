"""Admin Order Lifecycle, Verification, and Renewal Handlers."""

import logging
from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import OrderStatus
from bot.keyboards.inline_admin import get_admin_order_actions_keyboard, get_admin_orders_keyboard
from bot.keyboards.reply import get_cancel_keyboard
from bot.services.notification_service import NotificationService
from bot.services.order_service import OrderService
from bot.services.payment_service import PaymentService
from bot.services.user_service import UserService
from bot.states.admin_states import AdminOrderStates
from bot.utils.formatters import format_datetime, format_duration, format_price

logger = logging.getLogger(__name__)

router = Router(name="admin_orders_router")


@router.callback_query(F.data.startswith("adm_orders"))
async def handle_adm_orders(query: CallbackQuery, session: AsyncSession) -> None:
    """List orders with status filters."""
    is_admin = await UserService.is_admin(session, query.from_user.id)
    if not is_admin:
        await query.answer("دسترسی غیرمجاز.", show_alert=True)
        return

    filter_type = "all"
    status_filter = None
    if ":" in query.data:
        filter_type = query.data.split(":")[1]
        if filter_type == "pending_approval":
            status_filter = OrderStatus.PENDING_APPROVAL
        elif filter_type == "active":
            status_filter = OrderStatus.ACTIVE

    orders, total = await OrderService.list_orders(
        session=session,
        status_filter=status_filter,
        limit=20
    )

    text = (
        f"📦 <b>مدیریت سفارش‌ها ({total} مورد)</b>\n\n"
        f"فیلتر کنونی: <b>{filter_type}</b>\n"
        f"جهت بررسی و مدیریت، سفارش مورد نظر را انتخاب فرمایید:"
    )

    markup = get_admin_orders_keyboard(orders, current_filter=filter_type)
    try:
        await query.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    except Exception:
        await query.message.answer(text, parse_mode="HTML", reply_markup=markup)
    await query.answer()


@router.callback_query(F.data == "adm_order_search")
async def handle_adm_order_search(query: CallbackQuery, state: FSMContext) -> None:
    """Prompt admin for order code search."""
    await state.set_state(AdminOrderStates.search_code)
    await query.message.answer(
        "🔎 لطفاً <b>کد رهگیری سفارش</b> را ارسال فرمایید (مثال: ORD-AB12):",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()
    )
    await query.answer()


@router.message(AdminOrderStates.search_code)
async def handle_order_search_input(
    message: Message,
    state: FSMContext,
    session: AsyncSession
) -> None:
    """Find and display order by search code."""
    code = message.text.strip().upper()
    order = await OrderService.get_order_by_code(session, code)
    await state.clear()

    if not order:
        await message.answer(f"❌ سفارشی با کد «{code}» یافت نشد.")
        return

    await render_order_details_view(message, order)


@router.callback_query(F.data.startswith("adm_order_view:"))
async def handle_adm_order_view(query: CallbackQuery, session: AsyncSession) -> None:
    """Display single order details in admin panel."""
    order_id = int(query.data.split(":")[1])
    order = await OrderService.get_order_by_id(session, order_id)
    if not order:
        await query.answer("سفارش یافت نشد.", show_alert=True)
        return

    await render_order_details_view(query.message, order, edit=True)
    await query.answer()


async def render_order_details_view(message: Message, order, edit: bool = False) -> None:
    """Render full order review card for administrator."""
    # Find receipt photo if attached
    receipt_photo = None
    if order.payments:
        for p in order.payments:
            if p.receipt_photo_id:
                receipt_photo = p.receipt_photo_id
                break

    text = (
        f"📦 <b>بررسی سفارش {order.order_code}</b>\n\n"
        f"👤 کاربر: <b>{order.user.full_name}</b> (<code>{order.user_id}</code>)\n"
        f"⚡️ رک: <b>{order.rack.name}</b> (<code>{order.rack.code}</code>)\n"
        f"🛡 تگ کلن: <code>{order.rack.clan_tag or 'ندارد'}</code>\n"
        f"⏱ پلن: <b>{order.plan.title}</b> ({format_duration(order.plan.duration_hours)})\n"
        f"🏷 تگ بازیکن: <code>{order.player_tag or 'ندارد'}</code>\n"
        f"👤 نام اکانت بازی: <b>{order.player_name or 'ندارد'}</b>\n"
        f"💰 مبلغ نهایی: <b>{format_price(order.final_price)}</b>\n"
        f"📊 وضعیت: <b>{order.status.value}</b>\n"
        f"💳 روش پرداخت: <b>{order.payment_method.value}</b>\n"
        f"📅 تاریخ ثبت: {format_datetime(order.created_at)}\n"
        f"🟢 تاریخ شروع: {format_datetime(order.start_date)}\n"
        f"🔴 تاریخ پایان: {format_datetime(order.end_date)}\n"
    )

    if order.notes:
        text += f"📝 توضیحات کاربر: {order.notes}\n"
    if order.admin_notes:
        text += f"📌 یادداشت داخلی ادمین: {order.admin_notes}\n"

    markup = get_admin_order_actions_keyboard(order)

    if receipt_photo:
        try:
            await message.answer_photo(
                photo=receipt_photo,
                caption=text + "\n🖼 <i>تصویر فوق فیش واریزی ارسالی کاربر می‌باشد.</i>",
                parse_mode="HTML",
                reply_markup=markup
            )
            return
        except Exception:
            pass

    if edit:
        try:
            await message.edit_text(text, parse_mode="HTML", reply_markup=markup)
            return
        except Exception:
            pass

    await message.answer(text, parse_mode="HTML", reply_markup=markup)


@router.callback_query(F.data.startswith("adm_order_approve:"))
async def handle_adm_order_approve(
    query: CallbackQuery,
    session: AsyncSession,
    bot: Bot
) -> None:
    """Admin approves order: activates rental and notifies customer."""
    order_id = int(query.data.split(":")[1])
    order = await OrderService.get_order_by_id(session, order_id)

    if not order:
        await query.answer("سفارش یافت نشد.", show_alert=True)
        return

    # Approve payments if pending
    if order.payments:
        for p in order.payments:
            if p.status.value != "successful":
                p.status = p.status.__class__.SUCCESSFUL
                p.verified_by = query.from_user.id

    success, msg, approved_order = await OrderService.approve_order(
        session=session,
        order_id=order_id,
        admin_notes=f"تأیید شده توسط ادمین {query.from_user.id}"
    )

    if success and approved_order:
        await NotificationService.notify_order_approved(bot, approved_order)
        await query.answer("✅ سفارش با موفقیت تأیید و فعال شد.", show_alert=True)
        await render_order_details_view(query.message, approved_order, edit=True)
    else:
        await query.answer(msg, show_alert=True)


@router.callback_query(F.data.startswith("adm_order_cancel:"))
async def handle_adm_order_cancel(
    query: CallbackQuery,
    session: AsyncSession,
    bot: Bot
) -> None:
    """Cancel order and free rack capacity."""
    order_id = int(query.data.split(":")[1])
    success, msg, cancelled_order = await OrderService.cancel_order(
        session=session,
        order_id=order_id,
        reason=f"لغو توسط ادمین {query.from_user.id}"
    )

    if success and cancelled_order:
        await NotificationService.send_user_notification(
            bot=bot,
            user_id=cancelled_order.user_id,
            text=f"❌ <b>سفارش {cancelled_order.order_code} توسط مدیریت لغو گردید.</b>\nدر صورت کسر وجه یا نیاز به راهنمایی با پشتیبانی تماس بگیرید."
        )
        await query.answer("سفارش لغو شد.", show_alert=True)
        await render_order_details_view(query.message, cancelled_order, edit=True)
    else:
        await query.answer(msg, show_alert=True)


@router.callback_query(F.data.startswith("adm_order_renew:"))
async def handle_adm_order_renew(query: CallbackQuery, state: FSMContext) -> None:
    """Prompt admin for renewal duration hours."""
    order_id = int(query.data.split(":")[1])
    await state.update_data(renew_order_id=order_id)
    await state.set_state(AdminOrderStates.renew_hours)

    await query.message.answer(
        "🔄 <b>تمدید مدت اجاره سفارش</b>\n\n"
        "چند ساعت مایلید به مدت زمان این سفارش اضافه کنید؟ (مثال: برای ۲ روز عدد 48):",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()
    )
    await query.answer()


@router.message(AdminOrderStates.renew_hours)
async def handle_order_renew_hours_input(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot
) -> None:
    """Process extension hours for order."""
    text = message.text.strip()
    if not text.isdigit() or int(text) <= 0:
        await message.answer("❌ لطفاً یک عدد مثبت برای ساعت وارد فرمایید:")
        return

    hours = int(text)
    data = await state.get_data()
    order_id = data.get("renew_order_id")

    success, msg, renewed_order = await OrderService.renew_order(
        session=session,
        order_id=order_id,
        additional_hours=hours
    )

    await state.clear()
    if success and renewed_order:
        await NotificationService.send_user_notification(
            bot=bot,
            user_id=renewed_order.user_id,
            text=(
                f"🔄 <b>سفارش اجاره شما تمدید شد!</b>\n\n"
                f"▫️ کد سفارش: <code>{renewed_order.order_code}</code>\n"
                f"▫️ تمدید به میزان: <b>{hours} ساعت</b>\n"
                f"▫️ تاریخ پایان جدید: <b>{format_datetime(renewed_order.end_date)}</b>"
            )
        )
        await message.answer(f"✅ {msg}")
        await render_order_details_view(message, renewed_order)
    else:
        await message.answer(msg)


@router.callback_query(F.data.startswith("adm_order_msg:"))
async def handle_adm_order_msg(query: CallbackQuery, state: FSMContext) -> None:
    """Prompt admin for direct message to buyer."""
    order_id = int(query.data.split(":")[1])
    await state.update_data(msg_order_id=order_id)
    await state.set_state(AdminOrderStates.send_user_message)

    await query.message.answer(
        "✉️ <b>ارسال پیام اختصاصی به مشتری</b>\n\n"
        "متن پیامی که مایلید از طرف ربات برای این کاربر ارسال شود را بنویسید:",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()
    )
    await query.answer()


@router.message(AdminOrderStates.send_user_message)
async def handle_admin_direct_message(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot
) -> None:
    """Dispatch direct message to customer from admin."""
    content = message.text.strip()
    data = await state.get_data()
    order_id = data.get("msg_order_id")

    order = await OrderService.get_order_by_id(session, order_id)
    await state.clear()

    if not order:
        await message.answer("❌ سفارش یافت نشد.")
        return

    text_to_user = (
        f"📩 <b>پیام از طرف مدیریت در خصوص سفارش {order.order_code}:</b>\n\n"
        f"{content}\n\n"
        f"در صورت نیاز به پاسخ، از بخش ارتباط با پشتیبانی اقدام فرمایید."
    )

    sent = await NotificationService.send_user_notification(bot, order.user_id, text_to_user)
    if sent:
        await message.answer("✅ پیام شما با موفقیت برای خریدار ارسال شد.")
    else:
        await message.answer("❌ متأسفانه ارسال پیام به کاربر با خطا مواجه شد.")
