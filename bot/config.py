"""Application Configuration Module using Pydantic Settings."""

from typing import List
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Core application settings loaded from environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Telegram Bot Information
    bot_token: str = Field(..., alias="BOT_TOKEN", description="Telegram Bot API Token")
    bot_username: str = Field("@ClashRackRentalBot", alias="BOT_USERNAME")
    bot_name: str = Field("ربات اجاره رک کلش", alias="BOT_NAME")
    brand_name: str = Field("کلش رک پرشیا", alias="BRAND_NAME")
    bot_description: str = Field(
        "سیستم هوشمند و خودکار اجاره انواع رک و کلن دونیت کلش آف کلنز",
        alias="BOT_DESCRIPTION"
    )

    # Administrators and Support
    admin_ids: str = Field("123456789", alias="ADMIN_IDS", description="Comma-separated Telegram user IDs")
    support_id: int = Field(123456789, alias="SUPPORT_ID")
    support_username: str = Field("@ClashSupportAdmin", alias="SUPPORT_USERNAME")

    # Channels and Social Links
    main_channel_link: str = Field("https://t.me/clash_rack_official", alias="MAIN_CHANNEL_LINK")
    news_channel_link: str = Field("https://t.me/clash_rack_news", alias="NEWS_CHANNEL_LINK")
    rules_link: str = Field("https://t.me/clash_rack_rules", alias="RULES_LINK")
    contact_info: str = Field(
        "پشتیبانی ۲۴ ساعته: @ClashSupportAdmin | شماره تماس: 09120000000",
        alias="CONTACT_INFO"
    )

    # Financial & Payments
    currency: str = Field("تومان", alias="CURRENCY")
    payment_gateway: str = Field("zarinpal", alias="PAYMENT_GATEWAY")  # zarinpal, idpay, mock, card_to_card
    zarinpal_merchant_id: str = Field("00000000-0000-0000-0000-000000000000", alias="ZARINPAL_MERCHANT_ID")
    zarinpal_sandbox: bool = Field(True, alias="ZARINPAL_SANDBOX")

    # Card-to-Card Details
    card_number: str = Field("6037997000000000", alias="CARD_NUMBER")
    card_holder_name: str = Field("امیرمهدی رضایی", alias="CARD_HOLDER_NAME")
    bank_name: str = Field("بانک ملی ایران", alias="BANK_NAME")

    # Database Settings
    database_url: str = Field(
        "sqlite+aiosqlite:///./clash_rack.db",
        alias="DATABASE_URL"
    )

    # Business Logic Settings
    reservation_hold_minutes: int = Field(15, alias="RESERVATION_HOLD_MINUTES")
    rental_reminder_hours: str = Field("2,24", alias="RENTAL_REMINDER_HOURS")
    maintenance_mode: bool = Field(False, alias="MAINTENANCE_MODE")

    # Texts
    welcome_message: str = Field(
        "سلام به سامانه اجاره رک کلش خوش آمدید! ⚡️\nاز طریق منوی زیر می‌توانید انواع رک‌های دونیت، وار و مکس را مشاهده و به صورت آنی اجاره کنید.",
        alias="WELCOME_MESSAGE"
    )

    @property
    def admin_id_list(self) -> List[int]:
        """Parse comma-separated admin IDs string into a clean list of integers."""
        ids: List[int] = []
        for raw_id in self.admin_ids.split(","):
            cleaned = raw_id.strip()
            if cleaned.isdigit() or (cleaned.startswith("-") and cleaned[1:].isdigit()):
                ids.append(int(cleaned))
        if self.support_id and self.support_id not in ids:
            ids.append(self.support_id)
        return ids

    @property
    def reminder_hours_list(self) -> List[int]:
        """Parse comma-separated reminder hours into integers."""
        hours: List[int] = []
        for raw_h in self.rental_reminder_hours.split(","):
            cleaned = raw_h.strip()
            if cleaned.isdigit():
                hours.append(int(cleaned))
        return sorted(hours)

    def is_admin(self, user_id: int) -> bool:
        """Check if a specific Telegram user ID is an admin."""
        return user_id in self.admin_id_list


# Singleton instance
settings = Settings()
