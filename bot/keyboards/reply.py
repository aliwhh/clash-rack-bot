"""Reply Keyboards for main navigation."""

from typing import Dict
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

MAIN_MENU_TEXTS: Dict[str, str] = {
    "rent": "⚡ اجاره رک کلش",
    "order": "📅 رزرو و ثبت سفارش",
    "tariffs": "💰 مشاهده تعرفه‌ها",
    "calculator": "🧮 محاسبه هزینه اجاره",
    "my_orders": "📦 سفارش‌های من",
    "profile": "👤 حساب کاربری",
    "support": "💬 ارتباط با پشتیبانی",
    "rules": "📜 قوانین و مقررات",
    "admin": "⚙️ پنل مدیریت",
    "cancel": "❌ انصراف و بازگشت",
}


def get_main_menu_keyboard(is_admin: bool = False) -> ReplyKeyboardMarkup:
    """Generate persistent Reply Keyboard for main menu navigation."""
    keyboard = [
        [
            KeyboardButton(text=MAIN_MENU_TEXTS["rent"]),
            KeyboardButton(text=MAIN_MENU_TEXTS["order"]),
        ],
        [
            KeyboardButton(text=MAIN_MENU_TEXTS["tariffs"]),
            KeyboardButton(text=MAIN_MENU_TEXTS["calculator"]),
        ],
        [
            KeyboardButton(text=MAIN_MENU_TEXTS["my_orders"]),
            KeyboardButton(text=MAIN_MENU_TEXTS["profile"]),
        ],
        [
            KeyboardButton(text=MAIN_MENU_TEXTS["support"]),
            KeyboardButton(text=MAIN_MENU_TEXTS["rules"]),
        ],
    ]

    if is_admin:
        keyboard.append([KeyboardButton(text=MAIN_MENU_TEXTS["admin"])])

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        is_persistent=True,
    )


def get_cancel_keyboard() -> ReplyKeyboardMarkup:
    """Keyboard containing only cancel/back button during multi-step forms."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=MAIN_MENU_TEXTS["cancel"])]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
