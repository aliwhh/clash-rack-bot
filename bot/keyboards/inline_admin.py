"""Inline Keyboards for Administrator Panel."""

from typing import List
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.database.models import Channel, DiscountCode, Order, OrderStatus, Rack, RackStatus, SupportTicket, TicketStatus, User


def get_admin_dashboard_keyboard() -> InlineKeyboardMarkup:
    """Main administrative navigation dashboard."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⚡️ مدیریت رک‌ها و پلن‌ها", callback_data="adm_racks"),
            InlineKeyboardButton(text="📦 مدیریت سفارش‌ها", callback_data="adm_orders"),
        ],
        [
            InlineKeyboardButton(text="👥 مدیریت کاربران", callback_data="adm_users"),
            InlineKeyboardButton(text="📩 تیکت‌های پشتیبانی", callback_data="adm_tickets"),
        ],
        [
            InlineKeyboardButton(text="🎟 کدهای تخفیف", callback_data="adm_discounts"),
            InlineKeyboardButton(text="📢 ارسال پیام همگانی", callback_data="adm_broadcast"),
        ],
        [
            InlineKeyboardButton(text="⚙️ تنظیمات ربات و کانال‌ها", callback_data="adm_settings"),
            InlineKeyboardButton(text="📊 گزارش و خروجی اکسل", callback_data="adm_export_excel"),
        ],
        [
            InlineKeyboardButton(text="🔙 بستن پنل و خروج", callback_data="back_to_main")
        ]
    ])


def get_admin_racks_keyboard(racks: List[Rack]) -> InlineKeyboardMarkup:
    """List of racks in admin panel."""
    buttons = []
    buttons.append([
        InlineKeyboardButton(text="➕ افزودن رک جدید", callback_data="adm_rack_add")
    ])
    for rack in racks:
        status_tag = "فعال" if rack.is_active else "غیرفعال"
        buttons.append([
            InlineKeyboardButton(
                text=f"{rack.code} | {rack.name[:20]} ({status_tag})",
                callback_data=f"adm_rack_view:{rack.id}"
            )
        ])
    buttons.append([
        InlineKeyboardButton(text="🔙 بازگشت به داشبورد", callback_data="adm_dashboard")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_admin_rack_actions_keyboard(rack: Rack) -> InlineKeyboardMarkup:
    """Action buttons for a single rack."""
    toggle_text = "🔴 غیرفعال‌سازی" if rack.is_active else "🟢 فعال‌سازی"
    buttons = [
        [
            InlineKeyboardButton(text="➕ افزودن پلن زمانی", callback_data=f"adm_plan_add:{rack.id}"),
            InlineKeyboardButton(text=toggle_text, callback_data=f"adm_rack_toggle:{rack.id}"),
        ],
        [
            InlineKeyboardButton(text="✏️ ویرایش نام", callback_data=f"adm_rack_edit_name:{rack.id}"),
            InlineKeyboardButton(text="✏️ ویرایش تگ کلن", callback_data=f"adm_rack_edit_tag:{rack.id}"),
        ],
        [
            InlineKeyboardButton(text="✏️ ویرایش توضیحات", callback_data=f"adm_rack_edit_desc:{rack.id}"),
            InlineKeyboardButton(text="🖼 تغییر تصویر رک", callback_data=f"adm_rack_edit_photo:{rack.id}"),
        ],
        [
            InlineKeyboardButton(text="🗑 حذف رک", callback_data=f"adm_rack_delete:{rack.id}"),
        ],
        [
            InlineKeyboardButton(text="🔙 بازگشت به لیست رک‌ها", callback_data="adm_racks")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_admin_orders_keyboard(orders: List[Order], current_filter: str = "all") -> InlineKeyboardMarkup:
    """List orders for admin with status filter pills."""
    buttons = [
        [
            InlineKeyboardButton(text="همه", callback_data="adm_orders_filter:all"),
            InlineKeyboardButton(text="⏳ در انتظار بررسی", callback_data="adm_orders_filter:pending_approval"),
            InlineKeyboardButton(text="🟢 فعال", callback_data="adm_orders_filter:active"),
        ],
        [
            InlineKeyboardButton(text="🔎 جستجو با کد سفارش", callback_data="adm_order_search")
        ]
    ]

    for ord_obj in orders:
        buttons.append([
            InlineKeyboardButton(
                text=f"{ord_obj.order_code} | {ord_obj.user_id} ({ord_obj.status.value})",
                callback_data=f"adm_order_view:{ord_obj.id}"
            )
        ])

    buttons.append([
        InlineKeyboardButton(text="🔙 بازگشت به داشبورد", callback_data="adm_dashboard")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_admin_order_actions_keyboard(order: Order) -> InlineKeyboardMarkup:
    """Action buttons for single order in admin panel."""
    buttons = []
    if order.status in [OrderStatus.PENDING_APPROVAL, OrderStatus.PENDING_PAYMENT]:
        buttons.append([
            InlineKeyboardButton(text="✅ تأیید و فعال‌سازی اجاره", callback_data=f"adm_order_approve:{order.id}"),
            InlineKeyboardButton(text="❌ رد / لغو سفارش", callback_data=f"adm_order_cancel:{order.id}"),
        ])
    elif order.status == OrderStatus.ACTIVE:
        buttons.append([
            InlineKeyboardButton(text="🔄 تمدید مدت زمان", callback_data=f"adm_order_renew:{order.id}"),
            InlineKeyboardButton(text="⏹ پایان اجاره", callback_data=f"adm_order_complete:{order.id}"),
        ])

    buttons.append([
        InlineKeyboardButton(text="✉️ ارسال پیام به خریدار", callback_data=f"adm_order_msg:{order.id}"),
        InlineKeyboardButton(text="📝 ثبت یادداشت داخلی", callback_data=f"adm_order_notes:{order.id}"),
    ])
    buttons.append([
        InlineKeyboardButton(text="🔙 بازگشت به سفارش‌ها", callback_data="adm_orders")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_admin_users_keyboard(users: List[User]) -> InlineKeyboardMarkup:
    """List users for admin."""
    buttons = [
        [
            InlineKeyboardButton(text="🔎 جستجوی کاربر با شناسه/نام", callback_data="adm_user_search")
        ]
    ]
    for u in users:
        block_icon = "⛔️" if u.is_blocked else "👤"
        buttons.append([
            InlineKeyboardButton(
                text=f"{block_icon} {u.full_name[:18]} (ID: {u.id})",
                callback_data=f"adm_user_view:{u.id}"
            )
        ])
    buttons.append([
        InlineKeyboardButton(text="🔙 بازگشت به داشبورد", callback_data="adm_dashboard")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_admin_user_actions_keyboard(user: User) -> InlineKeyboardMarkup:
    """Action buttons for managing single user."""
    toggle_block_text = "🟢 رفع مسدودیت" if user.is_blocked else "⛔️ مسدود کردن کاربر"
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=toggle_block_text, callback_data=f"adm_user_toggle_block:{user.id}"),
            InlineKeyboardButton(text="📦 سفارش‌های کاربر", callback_data=f"adm_user_orders:{user.id}"),
        ],
        [
            InlineKeyboardButton(text="🔙 بازگشت به لیست کاربران", callback_data="adm_users")
        ]
    ])


def get_admin_discounts_keyboard(discounts: List[DiscountCode]) -> InlineKeyboardMarkup:
    """List of discount codes in admin."""
    buttons = [
        [
            InlineKeyboardButton(text="➕ ایجاد کد تخفیف جدید", callback_data="adm_discount_add")
        ]
    ]
    for disc in discounts:
        active_tag = "فعال" if disc.is_active else "غیرفعال"
        buttons.append([
            InlineKeyboardButton(
                text=f"🎟 {disc.code} ({disc.value} {disc.discount_type.value}) - {active_tag}",
                callback_data=f"adm_discount_view:{disc.id}"
            )
        ])
    buttons.append([
        InlineKeyboardButton(text="🔙 بازگشت به داشبورد", callback_data="adm_dashboard")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_admin_settings_keyboard(is_maintenance: bool) -> InlineKeyboardMarkup:
    """Bot settings configuration menu."""
    maint_text = "🔴 غیرفعال‌سازی حالت تعمیر" if is_maintenance else "🟢 فعال‌سازی حالت تعمیر"
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=maint_text, callback_data="adm_toggle_maintenance"),
        ],
        [
            InlineKeyboardButton(text="📢 کانال‌های عضویت اجباری", callback_data="adm_channels"),
            InlineKeyboardButton(text="💳 تنظیمات کارت بانکی", callback_data="adm_set_card"),
        ],
        [
            InlineKeyboardButton(text="📝 ویرایش متن خوش‌آمدگویی", callback_data="adm_set_welcome"),
            InlineKeyboardButton(text="⏱ مدت رزرو موقت", callback_data="adm_set_hold_time"),
        ],
        [
            InlineKeyboardButton(text="🔙 بازگشت به داشبورد", callback_data="adm_dashboard")
        ]
    ])


def get_admin_channels_keyboard(channels: List[Channel]) -> InlineKeyboardMarkup:
    """List of mandatory membership channels in admin."""
    buttons = [
        [
            InlineKeyboardButton(text="➕ افزودن کانال جدید", callback_data="adm_channel_add")
        ]
    ]
    for ch in channels:
        buttons.append([
            InlineKeyboardButton(
                text=f"📢 {ch.channel_name} ({ch.channel_id})",
                callback_data=f"adm_channel_view:{ch.id}"
            )
        ])
    buttons.append([
        InlineKeyboardButton(text="🔙 بازگشت به تنظیمات", callback_data="adm_settings")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_admin_ticket_actions_keyboard(ticket: SupportTicket) -> InlineKeyboardMarkup:
    """Action buttons for handling support ticket in admin."""
    buttons = []
    if ticket.status != TicketStatus.CLOSED:
        buttons.append([
            InlineKeyboardButton(text="✍️ ارسال پاسخ به کاربر", callback_data=f"adm_ticket_reply:{ticket.id}"),
            InlineKeyboardButton(text="🔒 بستن تیکت", callback_data=f"adm_ticket_close:{ticket.id}"),
        ])
    buttons.append([
        InlineKeyboardButton(text="🔙 بازگشت به تیکت‌ها", callback_data="adm_tickets")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)
