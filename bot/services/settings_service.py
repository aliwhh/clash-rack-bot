"""Bot Dynamic Settings and Mandatory Channel Management Service."""

import logging
from typing import Dict, List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.database.models import BotSetting, Channel

logger = logging.getLogger(__name__)


class SettingsService:
    """Service handling dynamic database-backed settings and channels."""

    @staticmethod
    async def get_setting(
        session: AsyncSession,
        key: str,
        default: Optional[str] = None
    ) -> Optional[str]:
        """Fetch setting value by key or fallback to default/config."""
        stmt = select(BotSetting).where(BotSetting.key == key)
        record = (await session.execute(stmt)).scalar_one_or_none()
        if record:
            return record.value
        # Fallback to pydantic config if matched
        if hasattr(settings, key):
            return str(getattr(settings, key))
        return default

    @staticmethod
    async def set_setting(
        session: AsyncSession,
        key: str,
        value: str,
        description: Optional[str] = None
    ) -> BotSetting:
        """Create or update dynamic setting."""
        stmt = select(BotSetting).where(BotSetting.key == key)
        record = (await session.execute(stmt)).scalar_one_or_none()
        if record:
            record.value = value
            if description:
                record.description = description
        else:
            record = BotSetting(key=key, value=value, description=description)
            session.add(record)
        await session.flush()
        logger.info("Setting '%s' updated to: %s", key, value)
        return record

    @staticmethod
    async def get_all_settings(session: AsyncSession) -> Dict[str, str]:
        """Return dict of all current settings."""
        stmt = select(BotSetting)
        records = (await session.execute(stmt)).scalars().all()
        return {r.key: r.value for r in records}

    @staticmethod
    async def is_maintenance_mode(session: AsyncSession) -> bool:
        """Check if bot is in maintenance mode."""
        val = await SettingsService.get_setting(session, "maintenance_mode", "false")
        return str(val).strip().lower() in ["true", "1", "yes"]

    @staticmethod
    async def get_mandatory_channels(
        session: AsyncSession,
        active_only: bool = True
    ) -> List[Channel]:
        """Fetch list of mandatory membership channels."""
        stmt = select(Channel)
        if active_only:
            stmt = stmt.where(Channel.is_active.is_(True))
        return list((await session.execute(stmt)).scalars().all())

    @staticmethod
    async def add_mandatory_channel(
        session: AsyncSession,
        channel_id: str,
        channel_name: str,
        invite_link: str
    ) -> Channel:
        """Add a new required channel."""
        clean_channel_id = channel_id.strip()
        stmt = select(Channel).where(Channel.channel_id == clean_channel_id)
        channel = (await session.execute(stmt)).scalar_one_or_none()
        if not channel:
            channel = Channel(
                channel_id=clean_channel_id,
                channel_name=channel_name.strip(),
                invite_link=invite_link.strip(),
                is_active=True,
            )
            session.add(channel)
        else:
            channel.channel_name = channel_name.strip()
            channel.invite_link = invite_link.strip()
            channel.is_active = True
        await session.flush()
        logger.info("Mandatory channel %s added/updated.", clean_channel_id)
        return channel

    @staticmethod
    async def delete_mandatory_channel(session: AsyncSession, channel_id: int) -> bool:
        """Remove a mandatory channel by internal ID."""
        stmt = select(Channel).where(Channel.id == channel_id)
        channel = (await session.execute(stmt)).scalar_one_or_none()
        if not channel:
            return False
        await session.delete(channel)
        await session.flush()
        return True
