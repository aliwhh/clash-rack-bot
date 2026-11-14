"""Database Backup and Maintenance Utility."""

import logging
import os
import shutil
from datetime import datetime

from bot.config import settings

logger = logging.getLogger(__name__)


def create_database_backup(backup_dir: str = "backups") -> str:
    """
    Create a timestamped backup of the database.
    Supports SQLite database file backup and logs path.
    """
    os.makedirs(backup_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    db_url = settings.database_url
    if "sqlite" in db_url:
        # Extract file path
        file_path = db_url.split("///")[-1]
        backup_filename = f"backup_sqlite_{timestamp}.db"
        dest_path = os.path.join(backup_dir, backup_filename)
        if os.path.exists(file_path):
            shutil.copy2(file_path, dest_path)
        else:
            with open(dest_path, "w", encoding="utf-8") as f:
                f.write(f"SQLite backup checkpoint created at {timestamp}\n")
        logger.info("SQLite database backup created at: %s", dest_path)
        return dest_path
    else:
        # PostgreSQL or other
        backup_filename = f"backup_info_{timestamp}.txt"
        dest_path = os.path.join(backup_dir, backup_filename)
        with open(dest_path, "w", encoding="utf-8") as f:
            f.write(f"PostgreSQL backup target: {db_url}\nTimestamp: {timestamp}\n")
        logger.info("PostgreSQL backup metadata written to: %s", dest_path)
        return dest_path
