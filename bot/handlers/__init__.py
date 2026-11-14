"""Bot Handlers and Routers Aggregation."""

from aiogram import Router

from bot.handlers.common import router as common_router
from bot.handlers.racks import router as racks_router
from bot.handlers.orders import router as orders_router
from bot.handlers.calculator import router as calculator_router
from bot.handlers.profile import router as profile_router
from bot.handlers.support import router as support_router
from bot.handlers.admin import admin_router

main_router = Router(name="main_application_router")
main_router.include_router(common_router)
main_router.include_router(racks_router)
main_router.include_router(orders_router)
main_router.include_router(calculator_router)
main_router.include_router(profile_router)
main_router.include_router(support_router)
main_router.include_router(admin_router)

__all__ = ["main_router"]
