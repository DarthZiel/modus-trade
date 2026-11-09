"""Durable reminders: run separately from HTTP workers, scan once per minute."""

import logging
import time

from sqlmodel import Session

from app.database import engine
from app.notifications import scan_reminders

logger = logging.getLogger(__name__)


def main():
    logging.basicConfig(level=logging.INFO)
    while True:
        try:
            with Session(engine) as db:
                scan_reminders(db)
        except Exception:
            logger.exception("Reminder scan failed; retrying in 60 seconds")
        time.sleep(60)


if __name__ == "__main__":
    main()
