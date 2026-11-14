"""Rack and Rental Plan management business logic service."""

import logging
from typing import Any, List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bot.database.models import Rack, RackStatus, RentalPlan

logger = logging.getLogger(__name__)


class RackService:
    """Service handling Clash racks and associated rental plans."""

    @staticmethod
    async def list_active_racks(session: AsyncSession) -> List[Rack]:
        """Fetch all active racks including their active rental plans."""
        stmt = (
            select(Rack)
            .options(
                selectinload(Rack.plans.and_(RentalPlan.is_active.is_(True)))
            )
            .where(
                Rack.is_active.is_(True),
                Rack.status != RackStatus.INACTIVE
            )
            .order_by(Rack.id.asc())
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def list_all_racks_admin(session: AsyncSession) -> List[Rack]:
        """Fetch all racks for admin management."""
        stmt = (
            select(Rack)
            .options(selectinload(Rack.plans))
            .order_by(Rack.id.desc())
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def get_rack_by_id(
        session: AsyncSession,
        rack_id: int,
        load_plans: bool = True
    ) -> Optional[Rack]:
        """Fetch rack by its primary key ID."""
        stmt = select(Rack).where(Rack.id == rack_id)
        if load_plans:
            stmt = stmt.options(selectinload(Rack.plans))
        return (await session.execute(stmt)).scalar_one_or_none()

    @staticmethod
    async def get_rack_by_code(session: AsyncSession, code: str) -> Optional[Rack]:
        """Fetch rack by its unique code."""
        stmt = select(Rack).options(selectinload(Rack.plans)).where(Rack.code == code)
        return (await session.execute(stmt)).scalar_one_or_none()

    @staticmethod
    async def create_rack(
        session: AsyncSession,
        name: str,
        code: str,
        description: str,
        clan_tag: Optional[str] = None,
        capacity: int = 1,
        photo_file_id: Optional[str] = None,
    ) -> Rack:
        """Create and store a new rack."""
        rack = Rack(
            name=name,
            code=code.upper(),
            clan_tag=clan_tag,
            description=description,
            capacity=capacity,
            photo_file_id=photo_file_id,
            status=RackStatus.AVAILABLE,
            is_active=True,
        )
        session.add(rack)
        await session.flush()
        logger.info("New rack created with ID %d and code %s", rack.id, rack.code)
        return rack

    @staticmethod
    async def update_rack(
        session: AsyncSession,
        rack_id: int,
        **kwargs: Any
    ) -> Optional[Rack]:
        """Update fields of an existing rack."""
        rack = await RackService.get_rack_by_id(session, rack_id, load_plans=False)
        if not rack:
            return None
        for key, value in kwargs.items():
            if hasattr(rack, key):
                setattr(rack, key, value)
        await session.flush()
        logger.info("Rack %d updated successfully.", rack_id)
        return rack

    @staticmethod
    async def delete_rack(session: AsyncSession, rack_id: int) -> bool:
        """Delete or deactivate rack."""
        rack = await RackService.get_rack_by_id(session, rack_id, load_plans=False)
        if not rack:
            return False
        await session.delete(rack)
        await session.flush()
        logger.info("Rack %d deleted.", rack_id)
        return True

    @staticmethod
    async def add_rental_plan(
        session: AsyncSession,
        rack_id: int,
        title: str,
        duration_hours: int,
        price: int,
        discount_percent: int = 0
    ) -> RentalPlan:
        """Add a rental pricing plan to a rack."""
        plan = RentalPlan(
            rack_id=rack_id,
            title=title,
            duration_hours=duration_hours,
            price=price,
            discount_percent=discount_percent,
            is_active=True,
        )
        session.add(plan)
        await session.flush()
        logger.info("Rental plan %d added to rack %d", plan.id, rack_id)
        return plan

    @staticmethod
    async def update_rental_plan(
        session: AsyncSession,
        plan_id: int,
        **kwargs: Any
    ) -> Optional[RentalPlan]:
        """Update an existing rental plan."""
        stmt = select(RentalPlan).where(RentalPlan.id == plan_id)
        plan = (await session.execute(stmt)).scalar_one_or_none()
        if not plan:
            return None
        for key, value in kwargs.items():
            if hasattr(plan, key):
                setattr(plan, key, value)
        await session.flush()
        return plan

    @staticmethod
    async def delete_rental_plan(session: AsyncSession, plan_id: int) -> bool:
        """Delete a rental plan."""
        stmt = select(RentalPlan).where(RentalPlan.id == plan_id)
        plan = (await session.execute(stmt)).scalar_one_or_none()
        if not plan:
            return False
        await session.delete(plan)
        await session.flush()
        return True

    @staticmethod
    async def get_plan_by_id(session: AsyncSession, plan_id: int) -> Optional[RentalPlan]:
        """Get rental plan by ID with associated rack loaded."""
        stmt = (
            select(RentalPlan)
            .options(selectinload(RentalPlan.rack))
            .where(RentalPlan.id == plan_id)
        )
        return (await session.execute(stmt)).scalar_one_or_none()
