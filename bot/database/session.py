"""Database Session and Connection Management Module."""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy import select

from bot.config import settings
from bot.database.models import (
    Base,
    Admin,
    AdminRole,
    BotSetting,
    Rack,
    RentalPlan,
    RackStatus,
)

logger = logging.getLogger(__name__)

_engine: Optional[AsyncEngine] = None
_session_factory: Optional[async_sessionmaker[AsyncSession]] = None


def get_engine() -> AsyncEngine:
    """Get or create singleton SQLAlchemy AsyncEngine."""
    global _engine
    if _engine is None:
        database_url = settings.database_url
        # SQLite specific tweaks for async
        is_sqlite = database_url.startswith("sqlite")
        connect_args = {"check_same_thread": False} if is_sqlite else {}

        _engine = create_async_engine(
            database_url,
            echo=False,
            future=True,
            pool_pre_ping=True,
            connect_args=connect_args,
        )
        logger.info("SQLAlchemy AsyncEngine initialized successfully.")
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Get or create singleton async_sessionmaker."""
    global _session_factory
    if _session_factory is None:
        engine = get_engine()
        _session_factory = async_sessionmaker(
            bind=engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
            autocommit=False,
        )
    return _session_factory


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Async context manager providing an isolated transactional database session."""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception as error:
            await session.rollback()
            logger.error("Database session transaction failed: %s", error, exc_info=True)
            raise


async def init_db() -> None:
    """Initialize database tables and seed initial required records."""
    engine = get_engine()
    logger.info("Starting database schema migration/creation...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database schema synchronized.")

    # Seed default data
    async with get_session() as session:
        # 1. Seed superadmins from settings
        for admin_id in settings.admin_id_list:
            stmt = select(Admin).where(Admin.user_id == admin_id)
            existing_admin = (await session.execute(stmt)).scalar_one_or_none()
            if not existing_admin:
                new_admin = Admin(
                    user_id=admin_id,
                    role=AdminRole.SUPERADMIN,
                )
                session.add(new_admin)
                logger.info("Seeded superadmin with Telegram ID: %d", admin_id)

        # 2. Seed initial Bot Settings
        default_settings = {
            "maintenance_mode": "false",
            "reservation_hold_minutes": str(settings.reservation_hold_minutes),
            "currency": settings.currency,
            "welcome_message": settings.welcome_message,
            "card_number": settings.card_number,
            "card_holder_name": settings.card_holder_name,
            "bank_name": settings.bank_name,
            "contact_info": settings.contact_info,
            "rules_link": settings.rules_link,
            "main_channel_link": settings.main_channel_link,
            "news_channel_link": settings.news_channel_link,
        }

        for key, val in default_settings.items():
            setting_stmt = select(BotSetting).where(BotSetting.key == key)
            existing_setting = (await session.execute(setting_stmt)).scalar_one_or_none()
            if not existing_setting:
                session.add(BotSetting(key=key, value=val, description=f"Default setting for {key}"))

        # 3. Seed demo rack if no racks exist
        racks_stmt = select(Rack)
        existing_racks = (await session.execute(racks_stmt)).scalars().first()
        if not existing_racks:
            demo_rack = Rack(
                name="رک کلن لول ۲۵ (سوپر دراگ و الکترو مکس)",
                code="RACK-101",
                clan_tag="#2Y90LVPG",
                description="⚡️ دونیت ۲۴ ساعته فوری تمام نیروها، ماشین‌های محاصره مکس و اسپل‌های ترکیبی وار.\n🏆 پرک کلن لول ۲۵ کامل و بوست دو لول دونیت.",
                status=RackStatus.AVAILABLE,
                capacity=1,
                is_active=True,
            )
            session.add(demo_rack)
            await session.flush()

            plans = [
                RentalPlan(rack_id=demo_rack.id, title="۱ روزه (تست)", duration_hours=24, price=25000),
                RentalPlan(rack_id=demo_rack.id, title="۳ روزه (وار لیگ)", duration_hours=72, price=65000),
                RentalPlan(rack_id=demo_rack.id, title="۷ روزه (هفتگی)", duration_hours=168, price=130000, discount_percent=10),
                RentalPlan(rack_id=demo_rack.id, title="۳۰ روزه (ماهانه اقتصادی)", duration_hours=720, price=450000, discount_percent=20),
            ]
            session.add_all(plans)
            logger.info("Seeded initial demo rack and rental plans.")


async def close_db() -> None:
    """Close and dispose of database connection pool."""
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        logger.info("Database engine disposed.")
