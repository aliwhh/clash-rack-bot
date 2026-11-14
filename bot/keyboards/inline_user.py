"""Inline Keyboards for Customer interactions."""

from typing import List
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.database.models import Order, OrderStatus, Rack, RackStatus, RentalPlan, SupportTicket, TicketStatus
from bot.utils.formatters import format_price


def get_racks_keyboard(racks: List[Rack]) -> InlineKeyboardMarkup:
    """Generate inline keyboard listing all available racks."""
    buttons = []
    for rack in racks:
        status_icon = "🟢" if rack.status == RackStatus.AVAILABLE else "🟡"
        buttons.append([
            InlineKeyboardButton(
                text=f"{status_icon} {rack.name} ({rack.code})",
                callback_data=f"rack_view:{rack.id}"
            )
        ])
    buttons.append([
        InlineKeyboardButton(text="🔙 بازگشت به منوی اصلی", callback_data="back_to_main")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_rack_details_keyboard(rack: Rack, plans: List[RentalPlan]) -> InlineKeyboardMarkup:
    """Keyboard on rack details view showing rental plans to book."""
    buttons = []
    if rack.status == RackStatus.AVAILABLE:
        for plan in plans:
            discount_badge = f" (-{plan.discount_percent}%)" if plan.discount_percent > 0 else ""
            buttons.append([
                InlineKeyboardButton(
                    text=f"⚡️ رزرو {plan.title} - {format_price(plan.final_price)}{discount_badge}",
                    callback_data=f"book_plan:{plan.id}"
                )
            ])
    buttons.append([
        InlineKeyboardButton(text="🔙 بازگشت به لیست رک‌ها", callback_data="view_all_racks")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_order_summary_keyboard(order_id: int, has_discount: bool = False) -> InlineKeyboardMarkup:
    """Keyboard for order review before payment."""
    buttons = []
    if not has_discount:
        buttons.append([
            InlineKeyboardButton(text="🎟 ثبت کد تخفیف", callback_data=f"apply_discount:{order_id}")
        ])
    buttons.append([
        InlineKeyboardButton(text="💳 رفتن به مرحله پرداخت", callback_data=f"proceed_pay:{order_id}")
    ])
    buttons.append([
        InlineKeyboardButton(text="❌ لغو سفارش", callback_data=f"cancel_order_user:{order_id}")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_payment_methods_keyboard(order_id: int, online_url: str = None) -> InlineKeyboardMarkup:
    """Keyboard offering payment gateway choices."""
    buttons = []
    if online_url:
        buttons.append([
            InlineKeyboardButton(text="🌐 پرداخت آنلاین با درگاه بانکی", url=online_url)
        ])
        buttons.append([
            InlineKeyboardButton(text="🔄 بررسی و تأیید پرداخت آنلاین", callback_data=f"verify_online:{order_id}")
        ])
    buttons.append([
        InlineKeyboardButton(text="💳 کارت به کارت (آپلود فیش واریزی)", callback_data=f"pay_c2c:{order_id}")
    ])
    buttons.append([
        InlineKeyboardButton(text="🔙 بازگشت به جزئیات سفارش", callback_data=f"view_order:{order_id}")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_user_orders_keyboard(orders: List[Order]) -> InlineKeyboardMarkup:
    """List of orders belonging to the user."""
    buttons = []
    status_icons = {
        OrderStatus.PENDING_PAYMENT: "⏳ در انتظار پرداخت",
        OrderStatus.PENDING_APPROVAL: "🔍 در حال بررسی فیش",
        OrderStatus.ACTIVE: "🟢 فعال",
        OrderStatus.COMPLETED: "✅ پایان یافته",
        OrderStatus.CANCELLED: "❌ لغو شده",
        OrderStatus.EXPIRED: "⌛️ منقضی شده",
    }
    for ord_obj in orders:
        badge = status_icons.get(ord_obj.status, ord_obj.status.value)
        buttons.append([
            InlineKeyboardButton(
                text=f"{ord_obj.order_code} | {ord_obj.rack.name[:18]}.. ({badge})",
                callback_data=f"view_order:{ord_obj.id}"
            )
        ])
    buttons.append([
        InlineKeyboardButton(text="🔙 بازگشت به منوی اصلی", callback_data="back_to_main")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_order_details_keyboard(order: Order) -> InlineKeyboardMarkup:
    """Buttons on specific order view."""
    buttons = []
    if order.status == OrderStatus.PENDING_PAYMENT:
        buttons.append([
            InlineKeyboardButton(text="💳 پرداخت سفارش", callback_data=f"proceed_pay:{order.id}")
        ])
        buttons.append([
            InlineKeyboardButton(text="❌ انصراف از سفارش", callback_data=f"cancel_order_user:{order.id}")
        ])
    elif order.status == OrderStatus.ACTIVE:
        buttons.append([
            InlineKeyboardButton(text="🔄 تمدید مدت اجاره", callback_data=f"renew_order_user:{order.id}")
        ])

    buttons.append([
        InlineKeyboardButton(text="💬 ارتباط با پشتیبانی در مورد این سفارش", callback_data=f"support_order:{order.order_code}")
    ])
    buttons.append([
        InlineKeyboardButton(text="🔙 بازگشت به لیست سفارش‌ها", callback_data="my_orders_list")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_calculator_racks_keyboard(racks: List[Rack]) -> InlineKeyboardMarkup:
    """Keyboard for selecting a rack in the interactive calculator."""
    buttons = []
    for rack in racks:
        buttons.append([
            InlineKeyboardButton(
                text=f"⚡️ {rack.name}",
                callback_data=f"calc_rack:{rack.id}"
            )
        ])
    buttons.append([
        InlineKeyboardButton(text="🔙 بازگشت به منوی اصلی", callback_data="back_to_main")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_calculator_plans_keyboard(plans: List[RentalPlan]) -> InlineKeyboardMarkup:
    """Keyboard for selecting plan in calculator."""
    buttons = []
    for plan in plans:
        buttons.append([
            InlineKeyboardButton(
                text=f"⏱ {plan.title} ({plan.duration_hours} ساعت) - {format_price(plan.final_price)}",
                callback_data=f"calc_plan:{plan.id}"
            )
        ])
    buttons.append([
        InlineKeyboardButton(text="🔙 بازگشت به محاسبه‌گر", callback_data="calc_start")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_support_menu_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for support menu."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📩 ارسال تیکت و پیام جدید", callback_data="ticket_new")
        ],
        [
            InlineKeyboardButton(text="📋 تیکت‌ها و گفتگوهای من", callback_data="ticket_my_list")
        ],
        [
            InlineKeyboardButton(text="🔙 بازگشت به منوی اصلی", callback_data="back_to_main")
        ]
    ])


def get_ticket_details_keyboard(ticket: SupportTicket) -> InlineKeyboardMarkup:
    """Keyboard on ticket conversation view."""
    buttons = []
    if ticket.status != TicketStatus.CLOSED:
        buttons.append([
            InlineKeyboardButton(text="✍️ ارسال پاسخ به تیکت", callback_data=f"ticket_reply:{ticket.id}")
        ])
        buttons.append([
            InlineKeyboardButton(text="🔒 بستن این تیکت", callback_data=f"ticket_close:{ticket.id}")
        ])
    buttons.append([
        InlineKeyboardButton(text="🔙 بازگشت به لیست تیکت‌ها", callback_data="ticket_my_list")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)
