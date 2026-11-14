"""Database Models for Clash of Clans Rack Rental Bot."""

from datetime import datetime
from enum import Enum
from typing import List, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""
    pass


# ==========================================
# Enumerations
# ==========================================

class AdminRole(str, Enum):
    """Admin role levels."""
    SUPERADMIN = "superadmin"
    ADMIN = "admin"
    SUPPORT = "support"


class RackStatus(str, Enum):
    """Rack availability status."""
    AVAILABLE = "available"      # موجود و آماده اجاره
    RESERVED = "reserved"        # رزرو موقت تا پرداخت
    RENTED = "rented"            # در حال استفاده و اجاره داده شده
    INACTIVE = "inactive"        # غیرفعال توسط ادمین


class OrderStatus(str, Enum):
    """Order lifecycle status."""
    PENDING_PAYMENT = "pending_payment"    # در انتظار پرداخت
    PENDING_APPROVAL = "pending_approval"  # در انتظار تأیید کارت به کارت توسط ادمین
    APPROVED = "approved"                  # تأیید شده (آماده فعال‌سازی)
    ACTIVE = "active"                      # فعال و در حال استفاده
    COMPLETED = "completed"                # تکمیل و پایان یافته
    CANCELLED = "cancelled"                # لغو شده
    EXPIRED = "expired"                    # منقضی شده


class PaymentStatus(str, Enum):
    """Payment transaction status."""
    PENDING = "pending"
    SUCCESSFUL = "successful"
    FAILED = "failed"
    REJECTED = "rejected"


class PaymentMethod(str, Enum):
    """Available payment methods."""
    ONLINE = "online"
    CARD_TO_CARD = "card_to_card"


class DiscountType(str, Enum):
    """Discount calculation type."""
    PERCENT = "percent"
    FIXED = "fixed"


class TicketStatus(str, Enum):
    """Support ticket status."""
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    ANSWERED = "answered"
    CLOSED = "closed"


# ==========================================
# ORM Models
# ==========================================

class User(Base):
    """Telegram User Profile Model."""
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    username: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    full_name: Mapped[str] = mapped_column(String(256), nullable=False)
    phone_number: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    # Relationships
    orders: Mapped[List["Order"]] = relationship("Order", back_populates="user", cascade="all, delete-orphan")
    tickets: Mapped[List["SupportTicket"]] = relationship("SupportTicket", back_populates="user", cascade="all, delete-orphan")
    reservations: Mapped[List["Reservation"]] = relationship("Reservation", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username} name={self.full_name}>"


class Admin(Base):
    """Administrators and Permissions Model."""
    __tablename__ = "admins"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    role: Mapped[AdminRole] = mapped_column(
        SQLEnum(AdminRole),
        default=AdminRole.ADMIN,
        nullable=False
    )
    added_by: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    def __repr__(self) -> str:
        return f"<Admin user_id={self.user_id} role={self.role}>"


class Rack(Base):
    """Clash of Clans Clan/Rack Entity."""
    __tablename__ = "racks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    clan_tag: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    photo_file_id: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    status: Mapped[RackStatus] = mapped_column(
        SQLEnum(RackStatus),
        default=RackStatus.AVAILABLE,
        nullable=False,
        index=True
    )
    capacity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    # Relationships
    plans: Mapped[List["RentalPlan"]] = relationship(
        "RentalPlan",
        back_populates="rack",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    orders: Mapped[List["Order"]] = relationship("Order", back_populates="rack")
    reservations: Mapped[List["Reservation"]] = relationship("Reservation", back_populates="rack")

    def __repr__(self) -> str:
        return f"<Rack id={self.id} code={self.code} name={self.name} status={self.status}>"


class RentalPlan(Base):
    """Duration and Pricing Plan for a Rack."""
    __tablename__ = "rental_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rack_id: Mapped[int] = mapped_column(Integer, ForeignKey("racks.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(128), nullable=False)  # e.g., '۳ روزه', '۱ هفته'
    duration_hours: Mapped[int] = mapped_column(Integer, nullable=False)  # Duration in hours
    price: Mapped[int] = mapped_column(Integer, nullable=False)  # Base price in Toman
    discount_percent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    rack: Mapped["Rack"] = relationship("Rack", back_populates="plans")
    orders: Mapped[List["Order"]] = relationship("Order", back_populates="plan")

    @property
    def final_price(self) -> int:
        """Calculate price after plan discount."""
        if self.discount_percent > 0:
            discount = int(self.price * (self.discount_percent / 100))
            return max(0, self.price - discount)
        return self.price

    def __repr__(self) -> str:
        return f"<RentalPlan id={self.id} rack_id={self.rack_id} title={self.title} price={self.price}>"


class Reservation(Base):
    """Temporary Rack Reservation during checkout to prevent race conditions."""
    __tablename__ = "reservations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rack_id: Mapped[int] = mapped_column(Integer, ForeignKey("racks.id", ondelete="CASCADE"), nullable=False)
    plan_id: Mapped[int] = mapped_column(Integer, ForeignKey("rental_plans.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    order_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("orders.id", ondelete="SET NULL"), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    # Relationships
    rack: Mapped["Rack"] = relationship("Rack", back_populates="reservations")
    user: Mapped["User"] = relationship("User", back_populates="reservations")
    plan: Mapped["RentalPlan"] = relationship("RentalPlan")

    def __repr__(self) -> str:
        return f"<Reservation id={self.id} rack_id={self.rack_id} user_id={self.user_id} active={self.is_active}>"


class Order(Base):
    """Rental Order Entity."""
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    rack_id: Mapped[int] = mapped_column(Integer, ForeignKey("racks.id", ondelete="RESTRICT"), nullable=False)
    plan_id: Mapped[int] = mapped_column(Integer, ForeignKey("rental_plans.id", ondelete="RESTRICT"), nullable=False)

    original_price: Mapped[int] = mapped_column(Integer, nullable=False)
    discount_amount: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    final_price: Mapped[int] = mapped_column(Integer, nullable=False)
    discount_code_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("discount_codes.id", ondelete="SET NULL"), nullable=True
    )

    status: Mapped[OrderStatus] = mapped_column(
        SQLEnum(OrderStatus),
        default=OrderStatus.PENDING_PAYMENT,
        nullable=False,
        index=True
    )
    payment_method: Mapped[PaymentMethod] = mapped_column(
        SQLEnum(PaymentMethod),
        default=PaymentMethod.ONLINE,
        nullable=False
    )

    start_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    end_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    player_tag: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    player_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    admin_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="orders")
    rack: Mapped["Rack"] = relationship("Rack", back_populates="orders")
    plan: Mapped["RentalPlan"] = relationship("RentalPlan", back_populates="orders")
    payments: Mapped[List["Payment"]] = relationship(
        "Payment",
        back_populates="order",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    discount_code: Mapped[Optional["DiscountCode"]] = relationship("DiscountCode")

    def __repr__(self) -> str:
        return f"<Order id={self.id} code={self.order_code} status={self.status} user_id={self.user_id}>"


class Payment(Base):
    """Payment Transaction Record."""
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(Integer, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    payment_method: Mapped[PaymentMethod] = mapped_column(SQLEnum(PaymentMethod), nullable=False)
    status: Mapped[PaymentStatus] = mapped_column(
        SQLEnum(PaymentStatus),
        default=PaymentStatus.PENDING,
        nullable=False,
        index=True
    )

    # Gateway or Receipt details
    authority: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    ref_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    card_number: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    receipt_photo_id: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    verified_by: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    # Relationships
    order: Mapped["Order"] = relationship("Order", back_populates="payments")

    def __repr__(self) -> str:
        return f"<Payment id={self.id} order_id={self.order_id} amount={self.amount} status={self.status}>"


class DiscountCode(Base):
    """Promotional Discount Code Entity."""
    __tablename__ = "discount_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    discount_type: Mapped[DiscountType] = mapped_column(
        SQLEnum(DiscountType),
        default=DiscountType.PERCENT,
        nullable=False
    )
    value: Mapped[int] = mapped_column(Integer, nullable=False)  # percent (e.g. 20) or fixed amount (e.g. 50000)
    max_discount: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    min_order_amount: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    usage_limit: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    used_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    per_user_limit: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    def calculate_discount(self, order_amount: int) -> int:
        """Calculate discount amount in Toman for a given order amount."""
        if not self.is_active:
            return 0
        if self.min_order_amount and order_amount < self.min_order_amount:
            return 0
        if self.expires_at and datetime.now(self.expires_at.tzinfo) > self.expires_at:
            return 0
        if self.usage_limit and self.used_count >= self.usage_limit:
            return 0

        if self.discount_type == DiscountType.PERCENT:
            discount = int(order_amount * (self.value / 100))
            if self.max_discount and discount > self.max_discount:
                discount = self.max_discount
            return min(order_amount, discount)
        else:  # FIXED
            return min(order_amount, self.value)

    def __repr__(self) -> str:
        return f"<DiscountCode code={self.code} type={self.discount_type} value={self.value}>"


class SupportTicket(Base):
    """Customer Support Ticket Entity."""
    __tablename__ = "support_tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticket_code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    subject: Mapped[str] = mapped_column(String(256), nullable=False)
    status: Mapped[TicketStatus] = mapped_column(
        SQLEnum(TicketStatus),
        default=TicketStatus.OPEN,
        nullable=False,
        index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="tickets")
    messages: Mapped[List["SupportMessage"]] = relationship(
        "SupportMessage",
        back_populates="ticket",
        cascade="all, delete-orphan",
        order_by="SupportMessage.created_at",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<SupportTicket code={self.ticket_code} status={self.status} user_id={self.user_id}>"


class SupportMessage(Base):
    """Individual Message within a Support Ticket."""
    __tablename__ = "support_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticket_id: Mapped[int] = mapped_column(Integer, ForeignKey("support_tickets.id", ondelete="CASCADE"), nullable=False, index=True)
    sender_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    is_from_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    photo_id: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    # Relationships
    ticket: Mapped["SupportTicket"] = relationship("SupportTicket", back_populates="messages")

    def __repr__(self) -> str:
        return f"<SupportMessage id={self.id} ticket_id={self.ticket_id} from_admin={self.is_from_admin}>"


class Channel(Base):
    """Mandatory Membership Channel Entity."""
    __tablename__ = "channels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    channel_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)  # e.g., '@clash_rack' or '-100...'
    channel_name: Mapped[str] = mapped_column(String(256), nullable=False)
    invite_link: Mapped[str] = mapped_column(String(512), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    def __repr__(self) -> str:
        return f"<Channel id={self.id} channel_id={self.channel_id} active={self.is_active}>"


class BotSetting(Base):
    """Dynamic Key-Value Bot Settings."""
    __tablename__ = "bot_settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    def __repr__(self) -> str:
        return f"<BotSetting key={self.key}>"


class AuditLog(Base):
    """Administrative and Security Audit Logs."""
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    admin_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    target_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    target_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True
    )

    def __repr__(self) -> str:
        return f"<AuditLog id={self.id} admin_id={self.admin_id} action={self.action}>"
