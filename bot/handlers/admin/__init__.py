"""Admin routers aggregation."""

from aiogram import Router

from bot.handlers.admin.dashboard import router as dashboard_router
from bot.handlers.admin.racks_admin import router as racks_admin_router
from bot.handlers.admin.orders_admin import router as orders_admin_router
from bot.handlers.admin.users_admin import router as users_admin_router
from bot.handlers.admin.discounts_admin import router as discounts_admin_router
from bot.handlers.admin.broadcast_admin import router as broadcast_admin_router
from bot.handlers.admin.settings_admin import router as settings_admin_router

admin_router = Router(name="main_admin_router")
admin_router.include_router(dashboard_router)
admin_router.include_router(racks_admin_router)
admin_router.include_router(orders_admin_router)
admin_router.include_router(users_admin_router)
admin_router.include_router(discounts_admin_router)
admin_router.include_router(broadcast_admin_router)
admin_router.include_router(settings_admin_router)

__all__ = ["admin_router"]
