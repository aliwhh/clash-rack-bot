"""Text formatting and generator helpers."""

import secrets
import string
from datetime import datetime
from typing import Optional


def persian_digits(text: str) -> str:
    """Convert English digits in string to Persian digits."""
    mapping = {
        '0': '۰', '1': '۱', '2': '۲', '3': '۳', '4': '۴',
        '5': '۵', '6': '۶', '7': '۷', '8': '۸', '9': '۹'
    }
    return "".join(mapping.get(char, char) for char in str(text))


def format_price(amount: int, currency: str = "تومان", to_persian: bool = False) -> str:
    """Format integer price with comma separators and currency suffix."""
    formatted = f"{amount:,}"
    if to_persian:
        formatted = persian_digits(formatted)
    return f"{formatted} {currency}"


def format_datetime(dt: Optional[datetime], include_time: bool = True) -> str:
    """Format datetime object into clean string."""
    if not dt:
        return "ثبت نشده"
    if include_time:
        return dt.strftime("%Y/%m/%d - %H:%M")
    return dt.strftime("%Y/%m/%d")


def generate_unique_code(prefix: str = "ORD", length: int = 6) -> str:
    """Generate a random alphanumeric uppercase tracking code."""
    chars = string.ascii_uppercase + string.digits
    # Remove ambiguous characters like O, 0, I, 1
    chars = chars.replace("O", "").replace("0", "").replace("I", "").replace("1", "")
    random_part = "".join(secrets.choice(chars) for _ in range(length))
    return f"{prefix}-{random_part}"


def format_duration(hours: int) -> str:
    """Format duration in hours to human readable Persian text."""
    if hours < 24:
        return f"{hours} ساعت"
    days = hours // 24
    remaining_hours = hours % 24
    if remaining_hours == 0:
        return f"{days} روز"
    return f"{days} روز و {remaining_hours} ساعت"
