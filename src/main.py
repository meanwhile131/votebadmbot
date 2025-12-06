import os
import logging
from enum import Enum
import time
import sqlite3
from pathlib import Path
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode, ChatType
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, filters, MessageHandler, CallbackQueryHandler


class UserConversationState(Enum):
    NONE = 0
    SETTING_TITLE = 1

Path("data").mkdir(parents=True, exist_ok=True)
db = sqlite3.connect('data/bot.db')
cur = db.cursor()
cur.execute("CREATE TABLE IF NOT EXISTS polls(id INTEGER PRIMARY KEY, owner INTEGER, title TEXT);")
cur.execute("CREATE TABLE IF NOT EXISTS votes(poll_id INTEGER, caster_id INTEGER, vote INTEGER, caster_name TEXT, timestamp INTEGER);")
db.commit()

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
token = os.getenv("BOT_TOKEN")
if not token:
    logging.critical("BOT_TOKEN environment variable not found")
    exit(1)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == ChatType.PRIVATE:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="""Команды:
/new - создать голосование
/results <code>номер_опроса</code> - посмотреть результаты опроса""", parse_mode=ParseMode.HTML)
        return
    if len(context.args) == 1:
        try:
            poll_id = int(context.args[0])
        except ValueError:
            await update.message.reply_text("Не правильно указан номер опроса.")
            return
        cursor = cur.execute("SELECT owner,title FROM polls WHERE id = ?", [poll_id])
        poll = cursor.fetchone()
        if poll is None:
            await update.message.reply_text("Не найден опрос.")
            return
        if poll[0] != update.effective_user.id:
            return
        title = poll[1]
        reply_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("Буду", callback_data=f"{poll_id} 1"),
             InlineKeyboardButton("Не буду", callback_data=f"{poll_id} 0"), ]
        ])
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f"{title} (#{poll_id})",
                                       reply_markup=reply_markup)


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
    await context.bot.send_message(chat_id=update.effective_chat.id, text=f"""Создан опрос #<code>{new_id}</code>.
Вы можете опубликовать его в группе используя ссылку: {poll_url}
Вы сможете посмотреть результаты командой:
/results <code>{new_id}</code>""", parse_mode=ParseMode.HTML)


async def vote_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    timestamp = int(time.time())
    query = update.callback_query
    caster_id = update.effective_user.id
    caster_name = f"{update.effective_user.first_name} {update.effective_user.last_name}"
    try:
        poll_id, vote = map(int, query.data.split())
        if vote not in [0, 1]:
            raise ValueError
    except ValueError:
        await query.answer("Ошибка данных голоса.")
        return
    cursor = cur.execute("SELECT 1 FROM polls WHERE id = ?;", [poll_id])
    poll_found = len(cursor.fetchall()) > 0
    if not poll_found:
        await query.answer("Не существует такого опроса.")
        return
    cursor = cur.execute("SELECT vote FROM votes WHERE poll_id = ? AND caster_id = ?;", [poll_id, caster_id])
    votes = cursor.fetchall()
    vote_exists = len(votes) > 0
    if vote_exists:
        existing_vote = votes[0]
        if vote == existing_vote[0]:
            await query.answer("Голос не изменен.")
            return
        cursor = cur.execute("UPDATE votes SET vote = ?, timestamp = ? WHERE poll_id = ? AND caster_id = ?;", [vote, timestamp, poll_id, caster_id])
        db.commit()
        if cursor.rowcount < 1:
            await query.answer("Ошибка сохранения голоса.")
            return
        await query.answer("Голос изменен.")
        return
    cursor = cur.execute("INSERT INTO votes(poll_id, caster_id, vote, caster_name, timestamp) VALUES(?,?,?,?,?);", [poll_id, caster_id, vote, caster_name, timestamp])
    db.commit()
    if cursor.rowcount < 1:
        await query.answer("Ошибка сохранения голоса.")
        return
    await query.answer("Голос сохранен.")

async def results(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 1:
        await context.bot.send_message(update.effective_chat.id, """Укажите опрос, для которого нужно посмотреть результаты:
/results <code>номер_опроса</code>""", parse_mode=ParseMode.HTML)
        return

    try:
        poll_id = int(context.args[0])
    except ValueError:
        await context.bot.send_message(update.effective_chat.id, "Номер опроса нужно указать как число.")
        return

    cursor = cur.execute("SELECT * FROM polls WHERE id = ?;", [poll_id])
    polls = cursor.fetchall()
    poll_found = len(polls) > 0
    if not poll_found:
        await context.bot.send_message(update.effective_chat.id, f"Опрос #<code>{poll_id}</code> не найден.", parse_mode=ParseMode.HTML)
        return
    poll = polls[0]
    if poll[1] != update.effective_user.id:
        await context.bot.send_message(update.effective_chat.id, f"Только создатель опроса может смотреть его результаты.")
        return
    msg = f"""Результаты опроса "{poll[2]}" (#<code>{poll_id}</code>):\n"""
    cursor = cur.execute("SELECT caster_name, vote, timestamp FROM votes WHERE poll_id = ? ORDER BY timestamp ASC;", [poll_id])
    votes = cursor.fetchall()
    for vote in votes:
        vote_text = "Буду" if vote[1] == 1 else "Не буду"
        caster = vote[0]
        timestamp = vote[2]
        time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp))
        msg += f"""<code>{time_str}</code> {caster}<code>: {vote_text}</code>\n"""
    await context.bot.send_message(update.effective_chat.id, msg, parse_mode=ParseMode.HTML)

if __name__ == '__main__':
    application = ApplicationBuilder().token(token).build()

    start_handler = CommandHandler('start', start)
    application.add_handler(start_handler)
    new_handler = CommandHandler('new', new, filters.ChatType.PRIVATE)
    application.add_handler(new_handler)
    message_handler = MessageHandler(filters.TEXT & (~filters.COMMAND) & filters.ChatType.PRIVATE, message)
    application.add_handler(message_handler)
    vote_button_handler = CallbackQueryHandler(vote_button)
    application.add_handler(vote_button_handler)
    results_handler = CommandHandler('results', results, filters.ChatType.PRIVATE)
    application.add_handler(results_handler)

    application.run_polling()
