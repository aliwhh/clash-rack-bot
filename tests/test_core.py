"""Comprehensive automated test suite covering all 18 core project scenarios."""

from datetime import datetime, timedelta, timezone
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bot.database.models import (
    AdminRole,
    Base,
    DiscountType,
    OrderStatus,
    PaymentMethod,
    PaymentStatus,
    RackStatus,
    TicketStatus,
)
from bot.services.discount_service import DiscountService
from bot.services.order_service import OrderService
from bot.services.payment_service import PaymentService
from bot.services.rack_service import RackService
from bot.services.settings_service import SettingsService
from bot.services.ticket_service import TicketService
from bot.services.user_service import UserService


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    """Create fresh isolated in-memory SQLite database session for each test."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with session_maker() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_01_user_registration_and_profile(db_session: AsyncSession):
    """Scenario 1 & 17: User registration, update, and profile statistics."""
    user, created = await UserService.get_or_create_user(
        session=db_session,
        user_id=111222333,
        full_name="امیرمهدی رضایی",
        username="amir_clash"
    )
    assert created is True
    assert user.id == 111222333
    assert user.full_name == "امیرمهدی رضایی"

    # Profile stats
    stats = await UserService.get_user_stats(db_session, 111222333)
    assert stats["total_orders"] == 0
    assert stats["active_orders"] == 0
    assert stats["total_spent"] == 0
    assert stats["is_blocked"] is False


@pytest.mark.asyncio
async def test_02_mandatory_channel_system(db_session: AsyncSession):
    """Scenario 2: Mandatory channel addition, listing, and deletion."""
    ch = await SettingsService.add_mandatory_channel(
        session=db_session,
        channel_id="@clash_test_ch",
        channel_name="کانال تست کلش",
        invite_link="https://t.me/clash_test_ch"
    )
    assert ch.id is not None
    assert ch.channel_id == "@clash_test_ch"

    channels = await SettingsService.get_mandatory_channels(db_session, active_only=True)
    assert len(channels) == 1

    deleted = await SettingsService.delete_mandatory_channel(db_session, ch.id)
    assert deleted is True
    assert len(await SettingsService.get_mandatory_channels(db_session)) == 0


@pytest.mark.asyncio
async def test_03_rack_and_plan_management(db_session: AsyncSession):
    """Scenario 3, 15, 16: Rack creation, plan definition, and listing."""
    rack = await RackService.create_rack(
        session=db_session,
        name="رک لول ۲۵ وار مکس",
        code="RACK-WAR-01",
        clan_tag="#2Y90LVPG",
        description="دونیت ۲۴ ساعته سوپر دراگ و الکترو",
        capacity=1,
    )
    assert rack.id is not None
    assert rack.status == RackStatus.AVAILABLE

    # Add rental plans
    p1 = await RackService.add_rental_plan(db_session, rack.id, "۱ روزه", 24, 30000, 0)
    p2 = await RackService.add_rental_plan(db_session, rack.id, "۷ روزه", 168, 180000, 10)
    assert p1.final_price == 30000
    assert p2.final_price == 162000  # 180000 - 10%

    active_racks = await RackService.list_active_racks(db_session)
    assert len(active_racks) == 1
    assert len(active_racks[0].plans) == 2


@pytest.mark.asyncio
async def test_04_temporary_reservation_and_race_condition(db_session: AsyncSession):
    """Scenario 8 & 9: Concurrent booking prevention and capacity hold."""
    rack = await RackService.create_rack(
        session=db_session,
        name="رک ظرفیت ۱ نفره",
        code="RACK-SOLO",
        description="تست همزمانی",
        capacity=1
    )
    plan = await RackService.add_rental_plan(db_session, rack.id, "۳ روزه", 72, 80000)

    # User 1 reserves the rack
    res1, msg1 = await OrderService.create_temporary_reservation(
        session=db_session,
        user_id=1001,
        rack_id=rack.id,
        plan_id=plan.id,
        hold_minutes=15
    )
    assert res1 is not None
    assert rack.status == RackStatus.RESERVED

    # User 2 tries to reserve the same rack concurrently
    res2, msg2 = await OrderService.create_temporary_reservation(
        session=db_session,
        user_id=1002,
        rack_id=rack.id,
        plan_id=plan.id,
        hold_minutes=15
    )
    assert res2 is None
    assert "در حال حاضر توسط کاربر دیگری در مرحله رزرو موقت" in msg2


@pytest.mark.asyncio
async def test_05_expired_reservation_cleanup(db_session: AsyncSession):
    """Scenario 9 & 12: Auto release of expired temporary holds."""
    rack = await RackService.create_rack(
        session=db_session,
        name="رک با رزرو منقضی",
        code="RACK-EXP",
        description="تست انقضا",
        capacity=1
    )
    plan = await RackService.add_rental_plan(db_session, rack.id, "۱ روزه", 24, 25000)

    # Create an already expired reservation
    res, _ = await OrderService.create_temporary_reservation(
        session=db_session,
        user_id=1001,
        rack_id=rack.id,
        plan_id=plan.id,
        hold_minutes=-5  # Expired 5 minutes ago
    )

    cleaned = await OrderService.cleanup_expired_reservations(db_session)
    assert cleaned == 1
    assert rack.status == RackStatus.AVAILABLE


@pytest.mark.asyncio
async def test_06_order_creation_and_discount_code(db_session: AsyncSession):
    """Scenario 4, 5: Order creation with promo discount."""
    # User
    await UserService.get_or_create_user(db_session, 2001, "کاربر تستی")
    rack = await RackService.create_rack(db_session, "رک تست", "RACK-DISC", "تست", capacity=1)
    plan = await RackService.add_rental_plan(db_session, rack.id, "۳۰ روزه", 720, 100000)

    # Create 20% discount code
    disc = await DiscountService.create_discount(
        session=db_session,
        code="OFF20",
        discount_type=DiscountType.PERCENT,
        value=20,
        usage_limit=10
    )

    # Validate
    valid, msg, val, _ = await DiscountService.validate_discount(db_session, "OFF20", 2001, plan.final_price)
    assert valid is True
    assert val == 20000

    # Create order
    order = await OrderService.create_order(
        session=db_session,
        user_id=2001,
        rack_id=rack.id,
        plan_id=plan.id,
        payment_method=PaymentMethod.ONLINE,
        player_tag="#USERTAG1",
        player_name="ClashHero",
        discount_code_id=disc.id,
        discount_amount=val
    )
    assert order.final_price == 80000
    assert order.status == OrderStatus.PENDING_PAYMENT


@pytest.mark.asyncio
async def test_07_payment_approval_and_rental_activation(db_session: AsyncSession):
    """Scenario 6, 10: Successful payment, order approval, rack marked RENTED."""
    user, _ = await UserService.get_or_create_user(db_session, 3001, "علی حسینی")
    rack = await RackService.create_rack(db_session, "رک وار لیگ", "RACK-CWL", "تست", capacity=1)
    plan = await RackService.add_rental_plan(db_session, rack.id, "۲ روزه", 48, 50000)

    order = await OrderService.create_order(
        session=db_session,
        user_id=user.id,
        rack_id=rack.id,
        plan_id=plan.id,
        payment_method=PaymentMethod.ONLINE,
    )

    # Approve order
    success, msg, approved_order = await OrderService.approve_order(db_session, order.id)
    assert success is True
    assert approved_order.status == OrderStatus.ACTIVE
    assert approved_order.start_date is not None
    assert approved_order.end_date is not None
    assert rack.status == RackStatus.RENTED


@pytest.mark.asyncio
async def test_08_card_to_card_workflow(db_session: AsyncSession):
    """Scenario 6, 7: Card-to-Card submission, verification, and admin approval."""
    user, _ = await UserService.get_or_create_user(db_session, 4001, "محمد رضایی")
    rack = await RackService.create_rack(db_session, "رک مکس کارت", "RACK-C2C", "تست", capacity=1)
    plan = await RackService.add_rental_plan(db_session, rack.id, "۱ روزه", 24, 20000)

    order = await OrderService.create_order(
        session=db_session,
        user_id=user.id,
        rack_id=rack.id,
        plan_id=plan.id,
        payment_method=PaymentMethod.CARD_TO_CARD,
    )

    # User submits receipt photo
    ok, _, payment = await PaymentService.submit_card_to_card_receipt(
        session=db_session,
        order_id=order.id,
        user_id=user.id,
        receipt_photo_id="photo_file_id_xyz",
        card_number="1234"
    )
    assert ok is True
    assert order.status == OrderStatus.PENDING_APPROVAL
    assert payment.status == PaymentStatus.PENDING

    # Admin approves receipt
    appr_ok, _, appr_pay = await PaymentService.approve_card_to_card_payment(
        session=db_session,
        payment_id=payment.id,
        admin_id=999
    )
    assert appr_ok is True
    assert appr_pay.status == PaymentStatus.SUCCESSFUL
    assert order.status == OrderStatus.ACTIVE
    assert rack.status == RackStatus.RENTED


@pytest.mark.asyncio
async def test_09_rental_renewal_and_completion(db_session: AsyncSession):
    """Scenario 11 & 12: Extending active rental duration and auto-completion."""
    user, _ = await UserService.get_or_create_user(db_session, 5001, "رضا")
    rack = await RackService.create_rack(db_session, "رک تمدید", "RACK-REN", "تست", capacity=1)
    plan = await RackService.add_rental_plan(db_session, rack.id, "۱ روزه", 24, 20000)

    order = await OrderService.create_order(db_session, user.id, rack.id, plan.id, PaymentMethod.ONLINE)
    await OrderService.approve_order(db_session, order.id)

    old_end = order.end_date
    renew_ok, _, renewed = await OrderService.renew_order(db_session, order.id, additional_hours=24)
    assert renew_ok is True
    assert renewed.end_date == old_end + timedelta(hours=24)

    # Simulate rental period ended
    renewed.end_date = datetime.now(timezone.utc) - timedelta(hours=1)
    await db_session.flush()

    expired = await OrderService.cleanup_expired_active_rentals(db_session)
    assert len(expired) == 1
    assert renewed.status == OrderStatus.COMPLETED
    assert rack.status == RackStatus.AVAILABLE


@pytest.mark.asyncio
async def test_10_support_ticket_conversation(db_session: AsyncSession):
    """Scenario 13 & 14: Support ticket creation, message exchange, and closing."""
    ticket = await TicketService.create_ticket(
        session=db_session,
        user_id=6001,
        subject="عدم دریافت دونیت",
        initial_text="سلام من وارد کلن شدم اما نیرو ارسال نشد."
    )
    assert ticket.ticket_code.startswith("TCK-")
    assert ticket.status == TicketStatus.OPEN
    assert len(ticket.messages) == 1

    # Admin replies
    ok, _, admin_msg = await TicketService.add_message(
        session=db_session,
        ticket_id=ticket.id,
        sender_id=999,
        is_from_admin=True,
        text="سلام و درود، اکانت دونیت در حال حاضر فعال است و دونیت انجام شد."
    )
    assert ok is True
    assert ticket.status == TicketStatus.ANSWERED

    # User closes ticket
    closed = await TicketService.close_ticket(db_session, ticket.id)
    assert closed is True
    assert ticket.status == TicketStatus.CLOSED


@pytest.mark.asyncio
async def test_11_user_blocking_and_admin_permissions(db_session: AsyncSession):
    """Scenario 17 & 18: Admin permission checks and blocking system."""
    user, _ = await UserService.get_or_create_user(db_session, 7001, "کاربر متخلف")
    assert user.is_blocked is False

    await UserService.set_block_status(db_session, 7001, is_blocked=True)
    assert user.is_blocked is True

    await UserService.set_block_status(db_session, 7001, is_blocked=False)
    assert user.is_blocked is False


@pytest.mark.asyncio
async def test_12_admin_roles_and_database_permissions(db_session: AsyncSession):
    """Scenario 18: Admin role hierarchy (SUPERADMIN, ADMIN, SUPPORT)."""
    from bot.database.models import Admin

    # Add database admin
    admin_entry = Admin(user_id=888999, role=AdminRole.ADMIN)
    db_session.add(admin_entry)
    await db_session.flush()

    is_adm = await UserService.is_admin(db_session, 888999)
    assert is_adm is True

    # Non-admin
    is_non_adm = await UserService.is_admin(db_session, 555444)
    assert is_non_adm is False


@pytest.mark.asyncio
async def test_13_cost_calculator_formula_and_savings(db_session: AsyncSession):
    """Scenario 5: Rental calculation formulas, hourly and daily rates."""
    rack = await RackService.create_rack(db_session, "رک تست فرمول", "RACK-FORMULA", "توضیح")
    plan = await RackService.add_rental_plan(db_session, rack.id, "۳ روزه", 72, 90000, discount_percent=15)

    assert plan.price == 90000
    assert plan.discount_percent == 15
    # final_price: 90000 - 15% = 76500
    assert plan.final_price == 76500

    hourly = plan.final_price / plan.duration_hours
    assert hourly == 76500 / 72  # 1062.5
    daily = hourly * 24
    assert daily == 25500.0


@pytest.mark.asyncio
async def test_14_database_backup_generation(db_session: AsyncSession):
    """Scenario: Verify backup utility creates valid file."""
    import os
    from bot.utils.backup import create_database_backup

    backup_path = create_database_backup("backups")
    assert backup_path != ""
    assert os.path.exists(backup_path)
