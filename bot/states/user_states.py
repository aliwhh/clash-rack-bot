"""User Finite State Machine (FSM) States."""

from aiogram.fsm.state import State, StatesGroup


class OrderStates(StatesGroup):
    """FSM states for rack rental and checkout process."""
    selecting_rack = State()
    selecting_plan = State()
    entering_player_tag = State()
    entering_player_name = State()
    entering_notes = State()
    applying_discount = State()
    confirming_order = State()
    uploading_receipt_photo = State()
    entering_sender_card = State()


class SupportStates(StatesGroup):
    """FSM states for support ticket submission and conversation."""
    entering_subject = State()
    entering_message = State()
    replying_to_ticket = State()


class CalculatorStates(StatesGroup):
    """FSM states for interactive cost calculation."""
    selecting_rack = State()
    selecting_plan = State()
    entering_quantity = State()
