import sqlite3
import time
from enum import Enum

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode, ChatType
from telegram.ext import ContextTypes, CommandHandler, filters, MessageHandler, CallbackQueryHandler


class UserConversationState(Enum):
    NONE = 0
    SETTING_TITLE = 1
    SETTING_POLL_ID_FOR_RESULT = 2


class Bot:
    db: sqlite3.Connection
    cursor: sqlite3.Cursor

    def __init__(self, db, application):
        self.db = db
        self.cursor = Bot.init_db(self.db)

        start_handler = CommandHandler('start', self.start)
        application.add_handler(start_handler)
        new_handler = CommandHandler('new', self.new, filters.ChatType.PRIVATE)
        application.add_handler(new_handler)
        message_handler = MessageHandler(filters.TEXT & (~filters.COMMAND) & filters.ChatType.PRIVATE, self.message)
        application.add_handler(message_handler)
        vote_button_handler = CallbackQueryHandler(self.vote_button)
        application.add_handler(vote_button_handler)
        results_handler = CommandHandler('results', self.results, filters.ChatType.PRIVATE)
        application.add_handler(results_handler)

    @staticmethod
    def init_db(database: sqlite3.Connection):
        cursor = database.cursor()
        cursor.execute("PRAGMA foreign_keys = ON;")
        cursor.execute("CREATE TABLE IF NOT EXISTS polls(id INTEGER PRIMARY KEY, owner INTEGER, title TEXT);")
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS votes(poll_id INTEGER, caster_id INTEGER, vote INTEGER, caster_name TEXT, timestamp INTEGER, FOREIGN KEY(poll_id) REFERENCES polls(id));")
        cursor.execute("CREATE TABLE IF NOT EXISTS admins(id INTEGER PRIMARY KEY);")
        database.commit()
        return cursor

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat.type == ChatType.PRIVATE:
            await context.bot.send_message(update.effective_chat.id, """Команды:
    /new - создать голосование
    /results - посмотреть результаты опроса""", ParseMode.HTML)
            return
        if len(context.args) == 1:
            try:
                poll_id = int(context.args[0])
            except ValueError:
                await update.message.reply_text("Не правильно указан номер опроса.")
                return
            cursor = self.cursor.execute("SELECT owner,title FROM polls WHERE id = ?", [poll_id])
            poll = cursor.fetchone()
            if poll is None:
                await update.message.reply_text("Не найден опрос.")
                return
            if poll[0] != update.effective_user.id:
                return
            title = poll[1]
            reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("Буду", callback_data=f"{poll_id} 1"),
                                                  InlineKeyboardButton("Не буду", callback_data=f"{poll_id} 0"), ]])
            await context.bot.send_message(update.effective_chat.id, f"{title} (#{poll_id})", reply_markup=reply_markup)

    async def new(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        cursor = self.cursor.execute("SELECT 1 FROM admins WHERE id = ?;", [user_id])
        is_admin = len(cursor.fetchall()) > 0
        if not is_admin:
            await context.bot.send_message(update.effective_chat.id,
                                           "Только администраторы бота могут создавать голосования.")
            return
        context.user_data["state"] = UserConversationState.SETTING_TITLE
        await context.bot.send_message(update.effective_chat.id, "Напишите заголовок опроса.")

    async def message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        state = context.user_data.get("state")
        if state == UserConversationState.SETTING_TITLE:
            cursor = self.cursor.execute("INSERT INTO polls(owner,title) VALUES(?,?) RETURNING id;",
                                         [update.effective_chat.id, update.message.text])
            new_id = cursor.fetchone()[0]
            self.db.commit()
            context.user_data["state"] = UserConversationState.NONE
            poll_url = f"https://t.me/{context.bot.username}?startgroup={new_id}"
            await context.bot.send_message(update.effective_chat.id, f"""Создан опрос #{new_id}.
Вы можете опубликовать его в группе используя ссылку: {poll_url}
Вы сможете посмотреть результаты командой:
/results""")
        elif state == UserConversationState.SETTING_POLL_ID_FOR_RESULT:
            try:
                poll_id = int(update.message.text)
            except ValueError:
                await context.bot.send_message(update.effective_chat.id, "Номер опроса нужно указать как число.")
                return

            cursor = self.cursor.execute("SELECT * FROM polls WHERE id = ?;", [poll_id])
            polls = cursor.fetchall()
            poll_found = len(polls) > 0
            if not poll_found:
                await context.bot.send_message(update.effective_chat.id, f"Опрос #{poll_id} не найден.")
                return
            poll = polls[0]
            if poll[1] != update.effective_user.id:
                await context.bot.send_message(update.effective_chat.id,
                                               f"Только создатель опроса может смотреть его результаты.")
                return
            msg = f'Результаты опроса "{poll[2]}" (#{poll_id}):\n'

            cursor = self.cursor.execute(
                "SELECT caster_name FROM votes WHERE poll_id = ? AND vote = 1 ORDER BY timestamp ASC;", [poll_id])
            votes_1 = cursor.fetchall()
            msg += f"\nБуду ({len(votes_1)}):<pre>\n"
            for idx, vote in enumerate(votes_1):
                caster = vote[0]
                msg += f"{idx+1}: {caster}\n"
            msg += "</pre>"

            cursor = self.cursor.execute(
                "SELECT caster_name FROM votes WHERE poll_id = ? AND vote = 0 ORDER BY timestamp ASC;", [poll_id])
            votes_0 = cursor.fetchall()
            msg += f"\nНе буду ({len(votes_0)}):<pre>\n"
            for idx, vote in enumerate(votes_0):
                caster = vote[0]
                msg += f"{idx+1}: {caster}\n"
            msg += "</pre>"
            context.user_data["state"] = UserConversationState.NONE
            await context.bot.send_message(update.effective_chat.id, msg, ParseMode.HTML)

    async def vote_button(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        cursor = self.cursor.execute("SELECT 1 FROM polls WHERE id = ?;", [poll_id])
        poll_found = len(cursor.fetchall()) > 0
        if not poll_found:
            await query.answer("Не существует такого опроса.")
            return
        cursor = self.cursor.execute("SELECT vote FROM votes WHERE poll_id = ? AND caster_id = ?;",
                                     [poll_id, caster_id])
        votes = cursor.fetchall()
        vote_exists = len(votes) > 0
        if vote_exists:
            existing_vote = votes[0]
            if vote == existing_vote[0]:
                await query.answer("Голос не изменен.")
                return
            cursor = self.cursor.execute(
                "UPDATE votes SET vote = ?, timestamp = ? WHERE poll_id = ? AND caster_id = ?;",
                [vote, timestamp, poll_id, caster_id])
            self.db.commit()
            if cursor.rowcount < 1:
                await query.answer("Ошибка сохранения голоса.")
                return
            await query.answer("Голос изменен.")
            return
        cursor = self.cursor.execute(
            "INSERT INTO votes(poll_id, caster_id, vote, caster_name, timestamp) VALUES(?,?,?,?,?);",
            [poll_id, caster_id, vote, caster_name, timestamp])
        self.db.commit()
        if cursor.rowcount < 1:
            await query.answer("Ошибка сохранения голоса.")
            return
        await query.answer("Голос сохранен.")

    @staticmethod
    async def results(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await context.bot.send_message(update.effective_chat.id,
                                       """Укажите номер опроса, для которого нужно посмотреть результаты.""")
        context.user_data["state"] = UserConversationState.SETTING_POLL_ID_FOR_RESULT
