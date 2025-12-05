import os
import logging
from enum import Enum
import sqlite3
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, filters, MessageHandler


class UserConversationState(Enum):
    NONE = 0
    SETTING_TITLE = 1


db = sqlite3.connect('bot.db')
cur = db.cursor()
cur.execute("CREATE TABLE IF NOT EXISTS polls(id INTEGER PRIMARY KEY, owner INTEGER, title TEXT);")
db.commit()

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.WARN
)
token = os.getenv("BOT_TOKEN")
if not token:
    logging.critical("BOT_TOKEN environment variable not found")
    exit(1)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == filters.ChatType.PRIVATE:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="""Команды:
/new - создать голосование""")
        return
    if len(context.args) == 1:
        try:
            poll_id = int(context.args[0])
        except ValueError:
            await update.message.reply_text("Не правильно указан номер опроса.")
            return
        cursor = cur.execute("SELECT owner,title FROM polls WHERE id = ?", [poll_id])
        poll = cursor.fetchone()
        print(poll, update.effective_chat.id)
        if poll is None:
            await update.message.reply_text("Не найден опрос.")
            return
        if poll[0] != update.effective_user.id:
            return
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f"тут будет опрос #{poll_id}")


async def new(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["state"] = UserConversationState.SETTING_TITLE
    await context.bot.send_message(chat_id=update.effective_chat.id, text="Напишите заголовок опроса.")


async def message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data["state"] != UserConversationState.SETTING_TITLE:
        return
    cursor = cur.execute("INSERT INTO polls(owner,title) VALUES(?,?) RETURNING id;",
                         [update.effective_chat.id, update.message.text])
    new_id = cursor.fetchone()[0]
    db.commit()
    context.user_data["state"] = UserConversationState.NONE
    poll_url = f"https://t.me/AnonymousPollBot?startgroup={new_id}"
    await context.bot.send_message(chat_id=update.effective_chat.id, text=f"""Создан опрос #{new_id}.
Вы можете опубликовать его в группе используя ссылку: {poll_url}""")


if __name__ == '__main__':
    application = ApplicationBuilder().token(token).build()

    start_handler = CommandHandler('start', start)
    application.add_handler(start_handler)
    new_handler = CommandHandler('new', new, filters.ChatType.PRIVATE)
    application.add_handler(new_handler)
    message_handler = MessageHandler(filters.TEXT & (~filters.COMMAND) & filters.ChatType.PRIVATE, message)
    application.add_handler(message_handler)

    application.run_polling()
