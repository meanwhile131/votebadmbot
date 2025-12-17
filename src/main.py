import logging
import os
import sqlite3
from pathlib import Path

from telegram.ext import ApplicationBuilder

from bot import Bot


def main():
    Path("data").mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect('data/bot.db')

    logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise ValueError("BOT_TOKEN environment variable not found")

    application = ApplicationBuilder().token(token).build()
    bot = Bot(db, application)
    application.run_polling(timeout=60)


if __name__ == '__main__':
    main()
