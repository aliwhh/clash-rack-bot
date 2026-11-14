"""Order processing and rental lifecycle service."""

import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bot.config import settings
from bot.database.models import (
    Order,
    OrderStatus,
    PaymentMethod,
    Rack,
    RackStatus,
    RentalPlan,
    Reservation,
)
from bot.utils.formatters import generate_unique_code

logger = logging.getLogger(__name__)


class OrderService:
    """Service handling order creation, temporary reservations, approval, and renewal."""

    @staticmethod
    async def check_rack_availability(session: AsyncSession, rack_id: int) -> Tuple[bool, str]:
        """
        Check if a rack is currently available for rental.
        Prevents race condition and concurrent reservation conflicts.
        """
        rack_stmt = select(Rack).where(Rack.id == rack_id)
        rack = (await session.execute(rack_stmt)).scalar_one_or_none()
        if not rack:
            return False, "❌ رک مورد نظر یافت نشد."
        if not rack.is_active or rack.status == RackStatus.INACTIVE:
            return False, "❌ این رک در حال حاضر غیرفعال است."
        if rack.status == RackStatus.RENTED:
            return False, "❌ این رک در حال حاضر اجاره داده شده است."

        # Check active temporary reservations
        now_utc = datetime.now(timezone.utc)
        res_stmt = select(func.count(Reservation.id)).where(
            Reservation.rack_id == rack_id,
            Reservation.is_active.is_(True),
            Reservation.expires_at > now_utc
        )
        active_res_count = (await session.execute(res_stmt)).scalar() or 0
        if active_res_count >= rack.capacity:
            return False, "⏳ این رک در حال حاضر توسط کاربر دیگری در مرحله رزرو موقت و پرداخت است."

        return True, "✅ رک آماده رزرو و اجاره است."

    @staticmethod
    async def create_temporary_reservation(
        session: AsyncSession,
        user_id: int,
        rack_id: int,
        plan_id: int,
        hold_minutes: int = 15
    ) -> Tuple[Optional[Reservation], str]:
        """Create a temporary hold to prevent concurrent booking conflicts."""
        is_avail, msg = await OrderService.check_rack_availability(session, rack_id)
        if not is_avail:
            return None, msg

        # Invalidate old reservations of this user for this rack
        old_res_stmt = select(Reservation).where(
            Reservation.user_id == user_id,
            Reservation.rack_id == rack_id,
            Reservation.is_active.is_(True)
        )
        old_reservations = (await session.execute(old_res_stmt)).scalars().all()
        for old_res in old_reservations:
            old_res.is_active = False

        expires_at = datetime.now(timezone.utc) + timedelta(minutes=hold_minutes)
        reservation = Reservation(
            rack_id=rack_id,
            plan_id=plan_id,
            user_id=user_id,
            expires_at=expires_at,
            is_active=True,
        )
        session.add(reservation)

        # Mark rack as reserved if at capacity
        rack = (await session.execute(select(Rack).where(Rack.id == rack_id))).scalar_one()
        rack.status = RackStatus.RESERVED

        await session.flush()
        logger.info("Temporary reservation %d created for user %d on rack %d", reservation.id, user_id, rack_id)
        return reservation, "رزرو موقت ثبت شد."

    @staticmethod
    async def create_order(
        session: AsyncSession,
        user_id: int,
        rack_id: int,
        plan_id: int,
        payment_method: PaymentMethod,
        player_tag: Optional[str] = None,
        player_name: Optional[str] = None,
        notes: Optional[str] = None,
        discount_code_id: Optional[int] = None,
        discount_amount: int = 0,
        reservation_id: Optional[int] = None,
    ) -> Order:
        """Create a formal order record."""
        plan_stmt = select(RentalPlan).where(RentalPlan.id == plan_id)
        plan = (await session.execute(plan_stmt)).scalar_one()

        original_price = plan.final_price
        final_price = max(0, original_price - discount_amount)
        order_code = generate_unique_code(prefix="ORD")

        order = Order(
            order_code=order_code,
            user_id=user_id,
            rack_id=rack_id,
            plan_id=plan_id,
            original_price=original_price,
            discount_amount=discount_amount,
            final_price=final_price,
            discount_code_id=discount_code_id,
            status=OrderStatus.PENDING_PAYMENT,
            payment_method=payment_method,
            player_tag=player_tag,
            player_name=player_name,
            notes=notes,
        )
        session.add(order)
        await session.flush()

        # Link reservation if provided
        if reservation_id:
            res_stmt = select(Reservation).where(Reservation.id == reservation_id)
            reservation = (await session.execute(res_stmt)).scalar_one_or_none()
            if reservation:
                reservation.order_id = order.id
                await session.flush()

        logger.info("Order %s created for user %d (Price: %d)", order_code, user_id, final_price)
        return order

    @staticmethod
    async def get_order_by_code(session: AsyncSession, order_code: str) -> Optional[Order]:
        """Fetch order by unique code with related entities loaded."""
        stmt = (
            select(Order)
            .options(
                selectinload(Order.rack),
                selectinload(Order.plan),
                selectinload(Order.user),
                selectinload(Order.payments),
                selectinload(Order.discount_code),
            )
            .where(Order.order_code == order_code.strip().upper())
        )
        return (await session.execute(stmt)).scalar_one_or_none()

    @staticmethod
    async def get_order_by_id(session: AsyncSession, order_id: int) -> Optional[Order]:
        """Fetch order by ID with related entities loaded."""
        stmt = (
            select(Order)
            .options(
                selectinload(Order.rack),
                selectinload(Order.plan),
                selectinload(Order.user),
                selectinload(Order.payments),
                selectinload(Order.discount_code),
            )
            .where(Order.id == order_id)
        )
        return (await session.execute(stmt)).scalar_one_or_none()

    @staticmethod
    async def get_user_orders(
        session: AsyncSession,
        user_id: int,
        status_filter: Optional[List[OrderStatus]] = None
    ) -> List[Order]:
        """Fetch orders belonging to a specific user."""
        stmt = (
            select(Order)
            .options(
                selectinload(Order.rack),
                selectinload(Order.plan),
            )
            .where(Order.user_id == user_id)
        )
        if status_filter:
            stmt = stmt.where(Order.status.in_(status_filter))
        stmt = stmt.order_by(Order.created_at.desc())
        return list((await session.execute(stmt)).scalars().all())

    @staticmethod
    async def list_orders(
        session: AsyncSession,
        status_filter: Optional[OrderStatus] = None,
        limit: int = 20,
        offset: int = 0,
        search_code: Optional[str] = None
    ) -> Tuple[List[Order], int]:
        """List orders with filtering and pagination for admin panel."""
        base_stmt = select(Order).options(
            selectinload(Order.rack),
            selectinload(Order.user),
            selectinload(Order.plan),
        )
        count_stmt = select(func.count(Order.id))

        if status_filter:
            base_stmt = base_stmt.where(Order.status == status_filter)
            count_stmt = count_stmt.where(Order.status == status_filter)

        if search_code:
            code_pattern = f"%{search_code.strip().upper()}%"
            base_stmt = base_stmt.where(Order.order_code.ilike(code_pattern))
            count_stmt = count_stmt.where(Order.order_code.ilike(code_pattern))

        total = (await session.execute(count_stmt)).scalar() or 0
        orders = (await session.execute(base_stmt.order_by(Order.created_at.desc()).limit(limit).offset(offset))).scalars().all()

        return list(orders), total

    @staticmethod
    async def approve_order(
        session: AsyncSession,
        order_id: int,
        admin_notes: Optional[str] = None
    ) -> Tuple[bool, str, Optional[Order]]:
        """
        Approve order: activates rental period, calculates start/end dates,
        and marks rack as RENTED.
        """
        order = await OrderService.get_order_by_id(session, order_id)
        if not order:
            return False, "❌ سفارش یافت نشد.", None

        if order.status in [OrderStatus.ACTIVE, OrderStatus.COMPLETED]:
            return False, "⚠️ این سفارش قبلاً فعال یا تکمیل شده است.", order

        now_utc = datetime.now(timezone.utc)
        duration_hours = order.plan.duration_hours
        end_date = now_utc + timedelta(hours=duration_hours)

        order.status = OrderStatus.ACTIVE
        order.start_date = now_utc
        order.end_date = end_date
        if admin_notes:
            order.admin_notes = admin_notes

        # Update rack status
        rack = order.rack
        rack.status = RackStatus.RENTED

        # Deactivate any lingering reservations for this order
        res_stmt = select(Reservation).where(Reservation.order_id == order.id)
        reservations = (await session.execute(res_stmt)).scalars().all()
        for res in reservations:
            res.is_active = False

        await session.flush()
        logger.info("Order %s approved and activated until %s", order.order_code, end_date)
        return True, "✅ سفارش با موفقیت تأیید و اجاره فعال گردید.", order

    @staticmethod
    async def cancel_order(
        session: AsyncSession,
        order_id: int,
        reason: Optional[str] = None
    ) -> Tuple[bool, str, Optional[Order]]:
        """Cancel an order and release rack and reservation."""
        order = await OrderService.get_order_by_id(session, order_id)
        if not order:
            return False, "❌ سفارش یافت نشد.", None

        order.status = OrderStatus.CANCELLED
        if reason:
            order.admin_notes = f"{order.admin_notes or ''}\nدلیل لغو: {reason}".strip()

        # Release reservations
        res_stmt = select(Reservation).where(Reservation.order_id == order.id)
        reservations = (await session.execute(res_stmt)).scalars().all()
        for res in reservations:
            res.is_active = False

        # If rack was reserved or rented for this order, restore availability
        rack = order.rack
        if rack.status in [RackStatus.RESERVED, RackStatus.RENTED]:
            rack.status = RackStatus.AVAILABLE

        await session.flush()
        logger.info("Order %s cancelled. Reason: %s", order.order_code, reason)
        return True, "✅ سفارش لغو گردید و رک آزاد شد.", order

    @staticmethod
    async def renew_order(
        session: AsyncSession,
        order_id: int,
        additional_hours: int
    ) -> Tuple[bool, str, Optional[Order]]:
        """Extend the rental period of an active order."""
        order = await OrderService.get_order_by_id(session, order_id)
        if not order:
            return False, "❌ سفارش یافت نشد.", None
        if order.status != OrderStatus.ACTIVE:
            return False, "❌ تنها سفارش‌های فعال قابل تمدید هستند.", order

        if order.end_date:
            order.end_date = order.end_date + timedelta(hours=additional_hours)
        else:
            order.end_date = datetime.now(timezone.utc) + timedelta(hours=additional_hours)

        await session.flush()
        logger.info("Order %s extended by %d hours. New end date: %s", order.order_code, additional_hours, order.end_date)
        return True, f"✅ مدت اجاره به میزان {additional_hours} ساعت با موفقیت تمدید شد.", order

    @staticmethod
    async def cleanup_expired_reservations(session: AsyncSession) -> int:
        """
        Background task: find expired temporary reservations and free up racks.
        """
        now_utc = datetime.now(timezone.utc)
        stmt = select(Reservation).where(
            Reservation.is_active.is_(True),
            Reservation.expires_at <= now_utc
        )
        expired_reservations = (await session.execute(stmt)).scalars().all()
        count = 0
        for res in expired_reservations:
            res.is_active = False
            # Check rack and cancel pending order if attached
            if res.order_id:
                order_stmt = select(Order).where(Order.id == res.order_id)
                order = (await session.execute(order_stmt)).scalar_one_or_none()
                if order and order.status == OrderStatus.PENDING_PAYMENT:
                    order.status = OrderStatus.EXPIRED

            # Release rack status if still marked reserved
            rack_stmt = select(Rack).where(Rack.id == res.rack_id)
            rack = (await session.execute(rack_stmt)).scalar_one_or_none()
            if rack and rack.status == RackStatus.RESERVED:
                rack.status = RackStatus.AVAILABLE

            count += 1

        if count > 0:
            await session.flush()
            logger.info("Cleaned up %d expired reservations.", count)
        return count

    @staticmethod
    async def cleanup_expired_active_rentals(session: AsyncSession) -> List[Order]:
        """
        Background task: find active orders whose rental period has ended,
        mark them as completed and return rack status to available.
        """
        now_utc = datetime.now(timezone.utc)
        stmt = (
            select(Order)
            .options(selectinload(Order.rack), selectinload(Order.user))
            .where(
                Order.status == OrderStatus.ACTIVE,
                Order.end_date <= now_utc
            )
        )
        expired_orders = list((await session.execute(stmt)).scalars().all())
        for order in expired_orders:
            order.status = OrderStatus.COMPLETED
            if order.rack:
                order.rack.status = RackStatus.AVAILABLE
            logger.info("Order %s rental period ended. Marked completed.", order.order_code)

        if expired_orders:
            await session.flush()
        return expired_orders

    @staticmethod
    async def get_expiring_rentals_for_reminder(
        session: AsyncSession,
        hours_before: int = 2
    ) -> List[Order]:
        """
        Find active orders that will expire within the next `hours_before` window.
        """
        now_utc = datetime.now(timezone.utc)
        window_end = now_utc + timedelta(hours=hours_before)
        stmt = (
            select(Order)
            .options(selectinload(Order.rack), selectinload(Order.user))
            .where(
                Order.status == OrderStatus.ACTIVE,
                Order.end_date > now_utc,
                Order.end_date <= window_end
            )
        )
        return list((await session.execute(stmt)).scalars().all())
