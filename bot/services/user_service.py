"""User management business logic service."""

import logging
from typing import Dict, List, Optional, Tuple

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.database.models import Admin, Order, OrderStatus, Payment, PaymentStatus, User

logger = logging.getLogger(__name__)


class UserService:
    """Service handling user accounts, profile statistics, and permissions."""

    @staticmethod
    async def get_or_create_user(
        session: AsyncSession,
        user_id: int,
        full_name: str,
        username: Optional[str] = None
    ) -> Tuple[User, bool]:
        """Fetch existing user or create a new user record."""
        stmt = select(User).where(User.id == user_id)
        user = (await session.execute(stmt)).scalar_one_or_none()
        created = False

        if not user:
            user = User(
                id=user_id,
                full_name=full_name,
                username=username,
            )
            session.add(user)
            await session.flush()
            created = True
            logger.info("New user registered: %d (@%s)", user_id, username or "no_username")
        else:
            # Keep profile info up-to-date
            updated = False
            if user.full_name != full_name:
                user.full_name = full_name
                updated = True
            if user.username != username:
                user.username = username
                updated = True
            if updated:
                await session.flush()

        return user, created

    @staticmethod
    async def get_user(session: AsyncSession, user_id: int) -> Optional[User]:
        """Get user by Telegram user ID."""
        stmt = select(User).where(User.id == user_id)
        return (await session.execute(stmt)).scalar_one_or_none()

    @staticmethod
    async def is_admin(session: AsyncSession, user_id: int) -> bool:
        """Check if user is an admin either in config or in database."""
        if settings.is_admin(user_id):
            return True
        stmt = select(Admin).where(Admin.user_id == user_id)
        admin = (await session.execute(stmt)).scalar_one_or_none()
        return admin is not None

    @staticmethod
    async def get_user_stats(session: AsyncSession, user_id: int) -> Dict[str, object]:
        """Calculate and return profile summary statistics for a user."""
        user = await UserService.get_user(session, user_id)
        if not user:
            return {}

        # Count total orders
        total_orders_stmt = select(func.count(Order.id)).where(Order.user_id == user_id)
        total_orders = (await session.execute(total_orders_stmt)).scalar() or 0

        # Count active orders
        active_orders_stmt = select(func.count(Order.id)).where(
            Order.user_id == user_id,
            Order.status.in_([OrderStatus.ACTIVE, OrderStatus.APPROVED])
        )
        active_orders = (await session.execute(active_orders_stmt)).scalar() or 0

        # Total successful payments amount
        total_spent_stmt = select(func.sum(Payment.amount)).where(
            Payment.user_id == user_id,
            Payment.status == PaymentStatus.SUCCESSFUL
        )
        total_spent = (await session.execute(total_spent_stmt)).scalar() or 0

        return {
            "user": user,
            "total_orders": total_orders,
            "active_orders": active_orders,
            "total_spent": int(total_spent),
            "is_blocked": user.is_blocked,
        }

    @staticmethod
    async def set_block_status(session: AsyncSession, user_id: int, is_blocked: bool) -> bool:
        """Block or unblock a user."""
        user = await UserService.get_user(session, user_id)
        if not user:
            return False
        user.is_blocked = is_blocked
        await session.flush()
        logger.info("User %d block status changed to: %s", user_id, is_blocked)
        return True

    @staticmethod
    async def list_users(
        session: AsyncSession,
        limit: int = 20,
        offset: int = 0,
        search_query: Optional[str] = None
    ) -> Tuple[List[User], int]:
        """List users with pagination and search."""
        base_stmt = select(User)
        count_stmt = select(func.count(User.id))

        if search_query:
            query_str = f"%{search_query.strip()}%"
            filter_clause = or_(
                User.full_name.ilike(query_str),
                User.username.ilike(query_str),
            )
            if search_query.strip().isdigit():
                filter_clause = or_(filter_clause, User.id == int(search_query.strip()))

            base_stmt = base_stmt.where(filter_clause)
            count_stmt = count_stmt.where(filter_clause)

        total_count = (await session.execute(count_stmt)).scalar() or 0
        users_stmt = base_stmt.order_by(User.created_at.desc()).limit(limit).offset(offset)
        users = (await session.execute(users_stmt)).scalars().all()

        return list(users), total_count
