"""Discount Code management and calculation service."""

import logging
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import DiscountCode, DiscountType, Order

logger = logging.getLogger(__name__)


class DiscountService:
    """Service handling promotional discount codes."""

    @staticmethod
    async def get_by_code(session: AsyncSession, code: str) -> Optional[DiscountCode]:
        """Fetch discount code model by code string (case-insensitive)."""
        clean_code = code.strip().upper()
        stmt = select(DiscountCode).where(DiscountCode.code == clean_code)
        return (await session.execute(stmt)).scalar_one_or_none()

    @staticmethod
    async def validate_discount(
        session: AsyncSession,
        code: str,
        user_id: int,
        order_amount: int
    ) -> Tuple[bool, str, int, Optional[DiscountCode]]:
        """
        Validate discount code against user and order amount.
        Returns: (is_valid, message, discount_amount, discount_object)
        """
        discount = await DiscountService.get_by_code(session, code)
        if not discount:
            return False, "❌ کد تخفیف وارد شده نامعتبر است.", 0, None

        if not discount.is_active:
            return False, "❌ این کد تخفیف در حال حاضر غیرفعال است.", 0, discount

        # Expiration check
        if discount.expires_at:
            now_utc = datetime.now(timezone.utc)
            # Normalize tzinfo if needed
            exp = discount.expires_at if discount.expires_at.tzinfo else discount.expires_at.replace(tzinfo=timezone.utc)
            if now_utc > exp:
                return False, "❌ مهلت استفاده از این کد تخفیف به پایان رسیده است.", 0, discount

        # Minimum order amount
        if discount.min_order_amount and order_amount < discount.min_order_amount:
            return (
                False,
                f"❌ حداقل مبلغ سفارش برای اعمال این کد {discount.min_order_amount:,} تومان است.",
                0,
                discount
            )

        # Global usage limit
        if discount.usage_limit and discount.used_count >= discount.usage_limit:
            return False, "❌ سقف استفاده کلی از این کد تخفیف پر شده است.", 0, discount

        # Per-user usage limit
        used_by_user_stmt = select(func.count(Order.id)).where(
            Order.user_id == user_id,
            Order.discount_code_id == discount.id,
            Order.status.not_in(["cancelled"])
        )
        used_by_user = (await session.execute(used_by_user_stmt)).scalar() or 0
        if used_by_user >= discount.per_user_limit:
            return False, "❌ شما قبلاً از این کد تخفیف استفاده کرده‌اید.", 0, discount

        # Calculate discount amount
        discount_amount = discount.calculate_discount(order_amount)
        if discount_amount <= 0:
            return False, "❌ این کد تخفیف برای سفارش شما قابل اعمال نیست.", 0, discount

        return True, "✅ کد تخفیف با موفقیت اعمال شد.", discount_amount, discount

    @staticmethod
    async def create_discount(
        session: AsyncSession,
        code: str,
        discount_type: DiscountType,
        value: int,
        max_discount: Optional[int] = None,
        min_order_amount: int = 0,
        usage_limit: Optional[int] = None,
        per_user_limit: int = 1,
        expires_at: Optional[datetime] = None
    ) -> DiscountCode:
        """Create a new discount code."""
        discount = DiscountCode(
            code=code.strip().upper(),
            discount_type=discount_type,
            value=value,
            max_discount=max_discount,
            min_order_amount=min_order_amount,
            usage_limit=usage_limit,
            per_user_limit=per_user_limit,
            expires_at=expires_at,
            is_active=True,
        )
        session.add(discount)
        await session.flush()
        logger.info("Discount code %s created.", discount.code)
        return discount

    @staticmethod
    async def list_discounts(session: AsyncSession) -> List[DiscountCode]:
        """Fetch all discount codes."""
        stmt = select(DiscountCode).order_by(DiscountCode.created_at.desc())
        return list((await session.execute(stmt)).scalars().all())

    @staticmethod
    async def increment_usage(session: AsyncSession, discount_id: int) -> None:
        """Increment used counter for a discount code."""
        stmt = select(DiscountCode).where(DiscountCode.id == discount_id)
        discount = (await session.execute(stmt)).scalar_one_or_none()
        if discount:
            discount.used_count += 1
            await session.flush()
