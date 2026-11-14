"""Keyboards package initialization."""

from bot.keyboards.reply import (
    get_main_menu_keyboard,
    get_cancel_keyboard,
    MAIN_MENU_TEXTS,
)
from bot.keyboards.inline_user import (
    get_racks_keyboard,
    get_rack_details_keyboard,
    get_payment_methods_keyboard,
    get_user_orders_keyboard,
    get_order_details_keyboard,
    get_calculator_racks_keyboard,
    get_calculator_plans_keyboard,
    get_support_menu_keyboard,
    get_ticket_details_keyboard,
)
from bot.keyboards.inline_admin import (
    get_admin_dashboard_keyboard,
    get_admin_racks_keyboard,
    get_admin_rack_actions_keyboard,
    get_admin_orders_keyboard,
    get_admin_order_actions_keyboard,
    get_admin_users_keyboard,
    get_admin_user_actions_keyboard,
    get_admin_discounts_keyboard,
    get_admin_settings_keyboard,
    get_admin_channels_keyboard,
    get_admin_ticket_actions_keyboard,
)

__all__ = [
    "get_main_menu_keyboard",
    "get_cancel_keyboard",
    "MAIN_MENU_TEXTS",
    "get_racks_keyboard",
    "get_rack_details_keyboard",
    "get_payment_methods_keyboard",
    "get_user_orders_keyboard",
    "get_order_details_keyboard",
    "get_calculator_racks_keyboard",
    "get_calculator_plans_keyboard",
    "get_support_menu_keyboard",
    "get_ticket_details_keyboard",
    "get_admin_dashboard_keyboard",
    "get_admin_racks_keyboard",
    "get_admin_rack_actions_keyboard",
    "get_admin_orders_keyboard",
    "get_admin_order_actions_keyboard",
    "get_admin_users_keyboard",
    "get_admin_user_actions_keyboard",
    "get_admin_discounts_keyboard",
    "get_admin_settings_keyboard",
    "get_admin_channels_keyboard",
    "get_admin_ticket_actions_keyboard",
]
