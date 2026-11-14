"""Support Ticket and Customer Messaging Service."""

import logging
from typing import List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bot.database.models import (
    SupportMessage,
    SupportTicket,
    TicketStatus,
)
from bot.utils.formatters import generate_unique_code

logger = logging.getLogger(__name__)


class TicketService:
    """Service handling support tickets, conversation threads, and ticket statuses."""

    @staticmethod
    async def create_ticket(
        session: AsyncSession,
        user_id: int,
        subject: str,
        initial_text: Optional[str] = None,
        photo_id: Optional[str] = None
    ) -> SupportTicket:
        """Create a new support ticket and attach the first customer message."""
        ticket_code = generate_unique_code(prefix="TCK")
        ticket = SupportTicket(
            ticket_code=ticket_code,
            user_id=user_id,
            subject=subject[:255],
            status=TicketStatus.OPEN,
        )
        session.add(ticket)
        await session.flush()

        if initial_text or photo_id:
            msg = SupportMessage(
                ticket_id=ticket.id,
                sender_id=user_id,
                is_from_admin=False,
                text=initial_text,
                photo_id=photo_id,
            )
            session.add(msg)
            await session.flush()

        logger.info("Support ticket %s created by user %d", ticket_code, user_id)
        return await TicketService.get_ticket(session, ticket.id)

    @staticmethod
    async def add_message(
        session: AsyncSession,
        ticket_id: int,
        sender_id: int,
        is_from_admin: bool,
        text: Optional[str] = None,
        photo_id: Optional[str] = None
    ) -> Tuple[bool, str, Optional[SupportMessage]]:
        """Append a message to an existing ticket and update ticket status."""
        stmt = select(SupportTicket).where(SupportTicket.id == ticket_id)
        ticket = (await session.execute(stmt)).scalar_one_or_none()
        if not ticket:
            return False, "❌ تیکت یافت نشد.", None

        if ticket.status == TicketStatus.CLOSED:
            return False, "❌ این تیکت بسته شده است و امکان ارسال پیام در آن وجود ندارد.", None

        msg = SupportMessage(
            ticket_id=ticket_id,
            sender_id=sender_id,
            is_from_admin=is_from_admin,
            text=text,
            photo_id=photo_id,
        )
        session.add(msg)

        # Update status based on who sent the message
        if is_from_admin:
            ticket.status = TicketStatus.ANSWERED
        else:
            ticket.status = TicketStatus.IN_PROGRESS

        await session.flush()
        return True, "✅ پیام با موفقیت ارسال شد.", msg

    @staticmethod
    async def get_ticket(session: AsyncSession, ticket_id: int) -> Optional[SupportTicket]:
        """Fetch ticket by ID with messages and user loaded."""
        stmt = (
            select(SupportTicket)
            .options(
                selectinload(SupportTicket.messages),
                selectinload(SupportTicket.user)
            )
            .where(SupportTicket.id == ticket_id)
        )
        return (await session.execute(stmt)).scalar_one_or_none()

    @staticmethod
    async def get_ticket_by_code(session: AsyncSession, ticket_code: str) -> Optional[SupportTicket]:
        """Fetch ticket by tracking code."""
        stmt = (
            select(SupportTicket)
            .options(
                selectinload(SupportTicket.messages),
                selectinload(SupportTicket.user)
            )
            .where(SupportTicket.ticket_code == ticket_code.strip().upper())
        )
        return (await session.execute(stmt)).scalar_one_or_none()

    @staticmethod
    async def get_user_tickets(session: AsyncSession, user_id: int) -> List[SupportTicket]:
        """Fetch all tickets submitted by a user."""
        stmt = (
            select(SupportTicket)
            .options(selectinload(SupportTicket.messages))
            .where(SupportTicket.user_id == user_id)
            .order_by(SupportTicket.created_at.desc())
        )
        return list((await session.execute(stmt)).scalars().all())

    @staticmethod
    async def list_tickets(
        session: AsyncSession,
        status_filter: Optional[TicketStatus] = None,
        limit: int = 20,
        offset: int = 0
    ) -> Tuple[List[SupportTicket], int]:
        """Fetch tickets for admin dashboard."""
        base_stmt = select(SupportTicket).options(
            selectinload(SupportTicket.user),
            selectinload(SupportTicket.messages),
        )
        count_stmt = select(func.count(SupportTicket.id))

        if status_filter:
            base_stmt = base_stmt.where(SupportTicket.status == status_filter)
            count_stmt = count_stmt.where(SupportTicket.status == status_filter)

        total = (await session.execute(count_stmt)).scalar() or 0
        tickets = (await session.execute(base_stmt.order_by(SupportTicket.updated_at.desc()).limit(limit).offset(offset))).scalars().all()

        return list(tickets), total

    @staticmethod
    async def close_ticket(session: AsyncSession, ticket_id: int) -> bool:
        """Close an active support ticket."""
        stmt = select(SupportTicket).where(SupportTicket.id == ticket_id)
        ticket = (await session.execute(stmt)).scalar_one_or_none()
        if not ticket:
            return False
        ticket.status = TicketStatus.CLOSED
        await session.flush()
        logger.info("Ticket %d closed.", ticket_id)
        return True
