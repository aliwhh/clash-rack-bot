"""Admin Finite State Machine (FSM) States."""

from aiogram.fsm.state import State, StatesGroup


class AdminRackStates(StatesGroup):
    """FSM states for creating and editing racks."""
    name = State()
    code = State()
    clan_tag = State()
    description = State()
    capacity = State()
    photo = State()
    edit_field_value = State()


class AdminPlanStates(StatesGroup):
    """FSM states for managing rental duration plans."""
    title = State()
    duration_hours = State()
    price = State()
    discount_percent = State()


class AdminOrderStates(StatesGroup):
    """FSM states for managing orders."""
    search_code = State()
    reject_reason = State()
    renew_hours = State()
    internal_notes = State()
    send_user_message = State()


class AdminUserStates(StatesGroup):
    """FSM states for managing bot users."""
    search_query = State()


class AdminTicketStates(StatesGroup):
    """FSM states for answering customer support tickets."""
    reply_message = State()


class AdminDiscountStates(StatesGroup):
    """FSM states for creating promotional discount codes."""
    code = State()
    discount_type = State()
    value = State()
    max_discount = State()
    min_order_amount = State()
    usage_limit = State()


class AdminBroadcastStates(StatesGroup):
    """FSM states for broadcasting announcements to all users."""
    message_content = State()
    confirm_send = State()


class AdminSettingsStates(StatesGroup):
    """FSM states for configuring bot variables."""
    edit_value = State()
    add_channel_id = State()
    add_channel_name = State()
    add_channel_link = State()
