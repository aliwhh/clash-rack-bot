"""Middleware initialization package."""

from bot.middlewares.db_middleware import DbSessionMiddleware
from bot.middlewares.auth_middleware import AuthMiddleware
from bot.middlewares.maintenance_middleware import MaintenanceMiddleware
from bot.middlewares.channel_join_middleware import ChannelJoinMiddleware

__all__ = [
    "DbSessionMiddleware",
    "AuthMiddleware",
    "MaintenanceMiddleware",
    "ChannelJoinMiddleware",
]
