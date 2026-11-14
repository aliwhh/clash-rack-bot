"""Customer Support Ticket and Messaging Handlers."""

import logging
from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.database.models import SupportTicket, TicketStatus
from bot.keyboards.inline_user import get_support_menu_keyboard, get_ticket_details_keyboard
from bot.keyboards.reply import MAIN_MENU_TEXTS, get_cancel_keyboard, get_main_menu_keyboard
from bot.services.notification_service import NotificationService
from bot.services.settings_service import SettingsService
from bot.services.ticket_service import TicketService
from bot.services.user_service import UserService
from bot.states.user_states import SupportStates
from bot.utils.formatters import format_datetime

logger = logging.getLogger(__name__)

router = Router(name="support_router")


@router.message(F.text == MAIN_MENU_TEXTS["support"])
async def handle_support_menu(message: Message, session: AsyncSession) -> None:
    """Display customer support options and direct contact information."""
    contact_info = await SettingsService.get_setting(session, "contact_info", default=settings.contact_info)

    text = (
        f"💬 <b>ارتباط با واحد پشتیبانی و مشاوره</b>\n\n"
        f"تیم پشتیبانی ما ۲۴ ساعته در خدمت شماست.\n"
        f"شما می‌توانید از طریق سیستم تیکت داخلی پیام خود را ارسال فرمایید یا مستقیماً ارتباط برقرار کنید.\n\n"
        f"📌 <b>اطلاعات تماس مستقیم:</b>\n{contact_info}\n\n"
        f"جهت ایجاد تیکت جدید یا پیگیری گفتگوهای قبلی از منوی زیر استفاده کنید:"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=get_support_menu_keyboard())


@router.callback_query(F.data == "ticket_new")
async def handle_ticket_new_callback(query: CallbackQuery, state: FSMContext) -> None:
    """Prompt user for ticket subject."""
    await state.set_state(SupportStates.entering_subject)
    await query.message.answer(
        "📩 <b>ثبت تیکت پشتیبانی جدید</b>\n\n"
        "لطفاً <b>موضوع تیکت</b> خود را وارد فرمایید (مثال: سوال در مورد نحوه دونیت رک، گزارش مشکل و ...):",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()
    )
    await query.answer()


@router.message(SupportStates.entering_subject)
async def handle_ticket_subject_input(message: Message, state: FSMContext) -> None:
    """Store ticket subject and prompt for message body."""
    subject = message.text.strip()
    await state.update_data(ticket_subject=subject)
    await state.set_state(SupportStates.entering_message)

    await message.answer(
        f"✅ موضوع: <b>{subject}</b>\n\n"
        f"لطفاً <b>متن کامل پیام</b> خود را ارسال فرمایید (می‌توانید عکس نیز ارسال کنید):",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()
    )


@router.message(SupportStates.entering_message)
async def handle_ticket_message_input(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot
) -> None:
    """Create support ticket and send notification to administrators."""
    data = await state.get_data()
    subject = data.get("ticket_subject", "درخواست پشتیبانی")

    text = message.text or message.caption
    photo_id = message.photo[-1].file_id if message.photo else None

    if not text and not photo_id:
        await message.answer("لطفاً یک متن یا تصویر برای پیام پشتیبانی ارسال نمایید:")
        return

    ticket = await TicketService.create_ticket(
        session=session,
        user_id=message.from_user.id,
        subject=subject,
        initial_text=text,
        photo_id=photo_id,
    )

    # Dispatch alert to administrators
    await NotificationService.notify_new_ticket(bot, ticket, text)

    await state.clear()
    is_admin = await UserService.is_admin(session, message.from_user.id)

    response_text = (
        f"✅ <b>تیکت پشتیبانی شما با موفقیت ثبت شد!</b>\n\n"
        f"▫️ کد رهگیری تیکت: <code>{ticket.ticket_code}</code>\n"
        f"▫️ موضوع: <b>{ticket.subject}</b>\n\n"
        f"پیام شما به دست کارشناسان پشتیبانی رسید و به زودی پاسخ آن از طریق همین ربات برای شما ارسال خواهد شد."
    )
    await message.answer(response_text, parse_mode="HTML", reply_markup=get_main_menu_keyboard(is_admin=is_admin))


@router.callback_query(F.data == "ticket_my_list")
async def handle_my_tickets_callback(query: CallbackQuery, session: AsyncSession) -> None:
    """Show list of tickets submitted by the user."""
    tickets = await TicketService.get_user_tickets(session, query.from_user.id)

    if not tickets:
        await query.answer("شما هیچ تیکت فعالی ندارید.", show_alert=True)
        return

    buttons = []
    status_emoji = {
        TicketStatus.OPEN: "🟢 باز",
        TicketStatus.IN_PROGRESS: "🟡 در حال بررسی",
        TicketStatus.ANSWERED: "🔔 پاسخ داده شده",
        TicketStatus.CLOSED: "🔒 بسته شده",
    }

    for t in tickets:
        badge = status_emoji.get(t.status, t.status.value)
        buttons.append([
            InlineKeyboardButton(
                text=f"{t.ticket_code} | {t.subject[:20]}.. ({badge})",
                callback_data=f"ticket_view:{t.id}"
            )
        ])

    buttons.append([
        InlineKeyboardButton(text="🔙 بازگشت به پشتیبانی", callback_data="back_to_support")
    ])

    markup = InlineKeyboardMarkup(inline_keyboard=buttons)
    text = "📋 <b>لیست تیکت‌های پشتیبانی شما:</b>\n\nجهت مشاهده متن گفتگو روی تیکت کلیک نمایید:"

    try:
        await query.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    except Exception:
        await query.message.answer(text, parse_mode="HTML", reply_markup=markup)
    await query.answer()


@router.callback_query(F.data == "back_to_support")
async def handle_back_to_support(query: CallbackQuery, session: AsyncSession) -> None:
    """Return to support root menu."""
    contact_info = await SettingsService.get_setting(session, "contact_info", default=settings.contact_info)
    text = (
        f"💬 <b>ارتباط با واحد پشتیبانی و مشاوره</b>\n\n"
        f"📌 <b>اطلاعات تماس مستقیم:</b>\n{contact_info}"
    )
    try:
        await query.message.edit_text(text, parse_mode="HTML", reply_markup=get_support_menu_keyboard())
    except Exception:
        await query.message.answer(text, parse_mode="HTML", reply_markup=get_support_menu_keyboard())
    await query.answer()


@router.callback_query(F.data.startswith("ticket_view:"))
async def handle_ticket_view_callback(query: CallbackQuery, session: AsyncSession) -> None:
    """Display conversation history of a single support ticket."""
    ticket_id = int(query.data.split(":")[1])
    ticket = await TicketService.get_ticket(session, ticket_id)

    if not ticket:
        await query.answer("❌ تیکت یافت نشد.", show_alert=True)
        return

    status_persian = {
        TicketStatus.OPEN: "🟢 باز و در انتظار پاسخ",
        TicketStatus.IN_PROGRESS: "🟡 در حال بررسی توسط ادمین",
        TicketStatus.ANSWERED: "🔔 پاسخ داده شده",
        TicketStatus.CLOSED: "🔒 بسته شده",
    }.get(ticket.status, ticket.status.value)

    header = (
        f"📩 <b>تیکت {ticket.ticket_code}</b>\n"
        f"▫️ موضوع: <b>{ticket.subject}</b>\n"
        f"▫️ وضعیت: <b>{status_persian}</b>\n"
        f"▫️ تاریخ ایجاد: {format_datetime(ticket.created_at)}\n"
        f"-----------------------------------------\n"
    )

    messages_text = ""
    for msg in ticket.messages:
        sender_label = "👨‍💼 پشتیبانی" if msg.is_from_admin else "👤 شما"
        body = msg.text or "(عکس پیوست)"
        messages_text += f"<b>{sender_label}</b> ({format_datetime(msg.created_at)}):\n{body}\n\n"

    full_text = header + (messages_text if messages_text else "پیامی در این تیکت وجود ندارد.")
    markup = get_ticket_details_keyboard(ticket)

    try:
        await query.message.edit_text(full_text, parse_mode="HTML", reply_markup=markup)
    except Exception:
        await query.message.answer(full_text, parse_mode="HTML", reply_markup=markup)
    await query.answer()


@router.callback_query(F.data.startswith("ticket_reply:"))
async def handle_ticket_reply_callback(query: CallbackQuery, state: FSMContext) -> None:
    """Prompt user for reply message to active ticket."""
    ticket_id = int(query.data.split(":")[1])
    await state.update_data(reply_ticket_id=ticket_id)
    await state.set_state(SupportStates.replying_to_ticket)

    await query.message.answer(
        "✍️ لطفاً <b>پاسخ یا پیام جدید</b> خود را ارسال فرمایید (متن یا عکس):",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()
    )
    await query.answer()


@router.message(SupportStates.replying_to_ticket)
async def handle_ticket_reply_input(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot
) -> None:
    """Store customer reply and notify admins."""
    data = await state.get_data()
    ticket_id = data.get("reply_ticket_id")

    text = message.text or message.caption
    photo_id = message.photo[-1].file_id if message.photo else None

    success, msg_result, _ = await TicketService.add_message(
        session=session,
        ticket_id=ticket_id,
        sender_id=message.from_user.id,
        is_from_admin=False,
        text=text,
        photo_id=photo_id,
    )

    if not success:
        await message.answer(msg_result)
        return

    ticket = await TicketService.get_ticket(session, ticket_id)
    alert_text = (
        f"📩 <b>پاسخ جدید کاربر در تیکت {ticket.ticket_code}!</b>\n\n"
        f"▫️ کاربر: <code>{message.from_user.id}</code>\n"
        f"▫️ موضوع: {ticket.subject}\n"
        f"▫️ متن پاسخ: {text or '(تصویر)'}"
    )
    await NotificationService.broadcast_to_admins(bot, alert_text)

    await state.clear()
    is_admin = await UserService.is_admin(session, message.from_user.id)

    await message.answer(
        "✅ پیام شما با موفقیت به تیکت اضافه شد و برای پشتیبانی ارسال گردید.",
        reply_markup=get_main_menu_keyboard(is_admin=is_admin)
    )


@router.callback_query(F.data.startswith("ticket_close:"))
async def handle_ticket_close_callback(query: CallbackQuery, session: AsyncSession) -> None:
    """Close an active ticket by user."""
    ticket_id = int(query.data.split(":")[1])
    await TicketService.close_ticket(session, ticket_id)
    await query.answer("🔒 تیکت با موفقیت بسته شد.", show_alert=True)
    try:
        await query.message.edit_text("🔒 این تیکت بسته شد.", parse_mode="HTML")
    except Exception:
        pass
