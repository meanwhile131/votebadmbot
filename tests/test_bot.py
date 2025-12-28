import sqlite3
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.bot import Bot, UserConversationState


@pytest.fixture(scope="function")
def db():
    db_connection = sqlite3.connect(':memory:')
    yield db_connection
    db_connection.close()


@pytest.fixture
def bot(db):
    mock_application = MagicMock()
    return Bot(db, mock_application)


@pytest.mark.asyncio
async def test_start_private_chat(bot):
    update = AsyncMock()
    update.effective_chat.id = 123
    update.effective_chat.type = 'private'
    context = MagicMock()
    context.bot.send_message = AsyncMock()

    await bot.start(update, context)

    context.bot.send_message.assert_called_once()
    sent_text = context.bot.send_message.call_args[0][1]
    assert "/new" in sent_text
    assert "/results" in sent_text


@pytest.mark.asyncio
async def test_start_group_chat_with_valid_poll_id(bot, db):
    update = AsyncMock()
    update.effective_chat.type = 'group'
    update.effective_user.id = 123
    context = MagicMock()
    context.bot.send_message = AsyncMock()
    context.args = ['1']
    cur = db.cursor()
    cur.execute("INSERT INTO polls(id, owner, title) VALUES(1, 123, 'Test Poll')")
    db.commit()

    await bot.start(update, context)

    context.bot.send_message.assert_called_once()
    sent_text = context.bot.send_message.call_args[0][1]
    assert "Test Poll" in sent_text
    assert "#1" in sent_text


@pytest.mark.asyncio
async def test_start_group_chat_with_no_args(bot):
    update = AsyncMock()
    update.effective_chat.type = 'group'
    update.effective_user.id = 123
    context = MagicMock()
    context.bot.send_message = AsyncMock()
    context.args = []

    await bot.start(update, context)

    context.bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_start_group_chat_with_invalid_arg(bot):
    update = AsyncMock()
    update.effective_chat.type = 'group'
    update.effective_user.id = 123
    context = MagicMock()
    context.bot.send_message = AsyncMock()
    context.args = ['abc']

    await bot.start(update, context)

    update.message.reply_text.assert_called_once()


@pytest.mark.asyncio
async def test_start_group_chat_with_incorrect_poll_id(bot, db):
    update = AsyncMock()
    update.effective_chat.type = 'group'
    update.effective_user.id = 123
    context = MagicMock()
    context.bot.send_message = AsyncMock()
    context.args = ['2']
    cur = db.cursor()
    cur.execute("INSERT INTO polls(id, owner, title) VALUES(1, 123, 'Test Poll')")
    db.commit()

    await bot.start(update, context)

    update.message.reply_text.assert_called_once()


@pytest.mark.asyncio
async def test_start_group_chat_with_different_owner(bot, db):
    update = AsyncMock()
    update.effective_chat.type = 'group'
    update.effective_user.id = 124
    context = MagicMock()
    context.bot.send_message = AsyncMock()
    context.args = ['1']
    cur = db.cursor()
    cur.execute("INSERT INTO polls(id, owner, title) VALUES(1, 123, 'Test Poll')")
    db.commit()

    await bot.start(update, context)

    update.message.reply_text.assert_not_called()


@pytest.mark.asyncio
async def test_new_as_admin(bot, db):
    update = AsyncMock()
    update.effective_user.id = 123
    update.effective_chat.id = 123
    context = MagicMock()
    context.bot.send_message = AsyncMock()
    context.user_data = {}
    cur = db.cursor()
    cur.execute("INSERT INTO admins(id) VALUES(123)")
    db.commit()

    await bot.new(update, context)

    context.bot.send_message.assert_called_once()
    assert context.user_data["state"] == UserConversationState.SETTING_TITLE


@pytest.mark.asyncio
async def test_new_as_non_admin(bot, db):
    update = AsyncMock()
    update.effective_user.id = 456
    update.effective_chat.id = 456
    context = MagicMock()
    context.bot.send_message = AsyncMock()
    context.user_data = {}

    await bot.new(update, context)

    context.bot.send_message.assert_called_once()
    assert context.user_data.get("state") != UserConversationState.SETTING_TITLE


@pytest.mark.asyncio
async def test_message_set_title(bot, db):
    update = AsyncMock()
    update.effective_chat.id = 123
    update.message.text = "My New Poll"
    context = MagicMock()
    context.bot.send_message = AsyncMock()
    context.bot.username = "TestBot"
    context.user_data = {"state": UserConversationState.SETTING_TITLE}

    await bot.message(update, context)

    context.bot.send_message.assert_called_once()
    sent_text = context.bot.send_message.call_args[0][1]
    assert "#1" in sent_text
    assert f"https://t.me/{context.bot.username}?startgroup=1" in sent_text
    assert context.user_data["state"] == UserConversationState.NONE
    cur = db.cursor()
    cur.execute("SELECT title FROM polls WHERE id = 1")
    assert cur.fetchone()[0] == "My New Poll"


@pytest.mark.asyncio
async def test_vote_button_new_vote(bot, db):
    update = AsyncMock()
    update.effective_user.id = 456
    update.effective_user.full_name = "John Doe"
    query = AsyncMock()
    query.data = "1 1"
    update.callback_query = query
    cur = db.cursor()
    cur.execute("INSERT INTO polls(id, owner, title) VALUES(1, 123, 'Test Poll')")
    db.commit()

    await bot.vote_button(update, MagicMock())

    query.answer.assert_called_once()
    assert "сохранен" in query.answer.call_args[0][0]
    cur.execute("SELECT vote FROM votes WHERE poll_id = 1 AND caster_id = 456")
    assert cur.fetchone()[0] == 1


@pytest.mark.asyncio
async def test_vote_button_change_vote(bot, db):
    update = AsyncMock()
    update.effective_user.id = 456
    update.effective_user.first_name = "John"
    update.effective_user.last_name = "Doe"
    query = AsyncMock()
    query.data = "1 0"
    update.callback_query = query
    cur = db.cursor()
    cur.execute("INSERT INTO polls(id, owner, title) VALUES(1, 123, 'Test Poll')")
    cur.execute(
        "INSERT INTO votes(poll_id, caster_id, vote, caster_name, timestamp) VALUES(1, 456, 1, 'John Doe', 12345)")
    db.commit()

    await bot.vote_button(update, MagicMock())

    query.answer.assert_called_once()
    assert "изменен" in query.answer.call_args[0][0]
    cur.execute("SELECT vote FROM votes WHERE poll_id = 1 AND caster_id = 456")
    assert cur.fetchone()[0] == 0


@pytest.mark.asyncio
async def test_vote_button_no_change_vote(bot, db):
    update = AsyncMock()
    update.effective_user.id = 456
    update.effective_user.first_name = "John"
    update.effective_user.last_name = "Doe"
    query = AsyncMock()
    query.data = "1 1"
    update.callback_query = query
    cur = db.cursor()
    cur.execute("INSERT INTO polls(id, owner, title) VALUES(1, 123, 'Test Poll')")
    cur.execute(
        "INSERT INTO votes(poll_id, caster_id, vote, caster_name, timestamp) VALUES(1, 456, 1, 'John Doe', 12345)")
    db.commit()

    await bot.vote_button(update, MagicMock())

    query.answer.assert_called_once()
    assert "не изменен" in query.answer.call_args[0][0]
    cur.execute("SELECT vote FROM votes WHERE poll_id = 1 AND caster_id = 456")
    assert cur.fetchone()[0] == 1


@pytest.mark.asyncio
async def test_vote_button_invalid_vote(bot, db):
    update = AsyncMock()
    update.effective_user.id = 456
    update.effective_user.first_name = "John"
    update.effective_user.last_name = "Doe"
    query = AsyncMock()
    query.data = "1 42"
    update.callback_query = query
    cur = db.cursor()
    cur.execute("INSERT INTO polls(id, owner, title) VALUES(1, 123, 'Test Poll')")
    db.commit()

    await bot.vote_button(update, MagicMock())

    query.answer.assert_called_once()
    assert "изменен" not in query.answer.call_args[0][0]
    cur.execute("SELECT vote FROM votes WHERE poll_id = 1 AND caster_id = 456")
    assert cur.fetchone() is None


@pytest.mark.asyncio
async def test_vote_button_invalid_poll(bot, db):
    update = AsyncMock()
    update.effective_user.id = 456
    update.effective_user.first_name = "John"
    update.effective_user.last_name = "Doe"
    query = AsyncMock()
    query.data = "42 1"
    update.callback_query = query
    cur = db.cursor()
    cur.execute("INSERT INTO polls(id, owner, title) VALUES(1, 123, 'Test Poll')")
    db.commit()

    await bot.vote_button(update, MagicMock())

    query.answer.assert_called_once()
    assert "изменен" not in query.answer.call_args[0][0]
    cur.execute("SELECT vote FROM votes WHERE poll_id = 1 AND caster_id = 456")
    assert cur.fetchone() is None


@pytest.mark.asyncio
async def test_start_results(bot):
    update = AsyncMock()
    update.effective_chat.id = 123
    context = MagicMock()
    context.bot.send_message = AsyncMock()
    context.user_data = {}

    await bot.results(update, context)

    context.bot.send_message.assert_called_once()
    assert context.user_data["state"] == UserConversationState.SETTING_POLL_ID_FOR_RESULT


@pytest.mark.asyncio
async def test_get_results_as_admin(bot, db):
    update = AsyncMock()
    update.effective_user.id = 1
    update.message.text = "1"
    context = MagicMock()
    context.bot.send_message = AsyncMock()
    context.user_data = {"state": UserConversationState.SETTING_POLL_ID_FOR_RESULT}
    cur = db.cursor()
    cur.execute("INSERT INTO polls(id, owner, title) VALUES(1, 123, 'Test Poll')")
    cur.execute("INSERT INTO admins(id) VALUES(1)")
    cur.execute("""INSERT INTO votes(poll_id, caster_id, vote, caster_name, timestamp) VALUES
                (1, 456, 1, 'John Doe', 12348),
                (1, 457, 1, 'James Smith', 12345),
                (1, 458, 0, 'Robert Williams', 12346),
                (1, 459, 0, 'Maria Garcia', 12347);""")
    db.commit()

    await bot.message(update, context)

    context.bot.send_message.assert_called_once()
    sent_text = context.bot.send_message.call_args[0][1]
    assert "John Doe" in sent_text
    assert "James Smith" in sent_text
    assert "Robert Williams" in sent_text
    assert "Maria Garcia" in sent_text

    # check ordered by timestamp
    assert sent_text.index("James Smith") < sent_text.index("John Doe")
    assert sent_text.index("Robert Williams") < sent_text.index("Maria Garcia")

    # check ordered by vote
    assert sent_text.index("John Doe") < sent_text.index("Maria Garcia")


@pytest.mark.asyncio
async def test_get_results_with_invalid_arg(bot, db):
    update = AsyncMock()
    update.effective_user.id = 123
    context = MagicMock()
    context.bot.send_message = AsyncMock()
    update.message.text = 'abc'
    context.user_data = {"state": UserConversationState.SETTING_POLL_ID_FOR_RESULT}
    cur = db.cursor()
    cur.execute("INSERT INTO admins(id) VALUES(123)")
    cur.execute("INSERT INTO polls(id, owner, title) VALUES(1, 123, 'Test Poll')")
    db.commit()

    await bot.message(update, context)

    context.bot.send_message.assert_called_once()
    sent_text = context.bot.send_message.call_args[0][1]
    assert "Test Poll" not in sent_text
    assert "abc" not in sent_text


@pytest.mark.asyncio
async def test_get_results_with_incorrect_poll_id(bot, db):
    update = AsyncMock()
    update.effective_user.id = 123
    context = MagicMock()
    context.bot.send_message = AsyncMock()
    update.message.text = '2'
    context.user_data = {"state": UserConversationState.SETTING_POLL_ID_FOR_RESULT}
    cur = db.cursor()
    cur.execute("INSERT INTO admins(id) VALUES(123)")
    cur.execute("INSERT INTO polls(id, owner, title) VALUES(1, 123, 'Test Poll')")
    db.commit()

    await bot.message(update, context)

    context.bot.send_message.assert_called_once()
    sent_text = context.bot.send_message.call_args[0][1]
    assert "Test Poll" not in sent_text


@pytest.mark.asyncio
async def test_get_results_as_admin_non_owner(bot, db):
    update = AsyncMock()
    update.effective_user.id = 2
    update.message.text = "1"
    context = MagicMock()
    context.bot.send_message = AsyncMock()
    context.user_data = {"state": UserConversationState.SETTING_POLL_ID_FOR_RESULT}
    cur = db.cursor()
    cur.execute("INSERT INTO polls(id, owner, title) VALUES(1, 124, 'Test Poll')")
    cur.execute("INSERT INTO admins(id) VALUES(2)")
    cur.execute("""INSERT INTO votes(poll_id, caster_id, vote, caster_name, timestamp) VALUES
                (1, 456, 1, 'John Doe', 12348),
                (1, 457, 1, 'James Smith', 12345),
                (1, 458, 0, 'Robert Williams', 12346),
                (1, 459, 0, 'Maria Garcia', 12347);""")
    db.commit()

    await bot.message(update, context)

    context.bot.send_message.assert_called_once()
    sent_text = context.bot.send_message.call_args[0][1]
    sent_text = context.bot.send_message.call_args[0][1]
    assert "John Doe" in sent_text
    assert "James Smith" in sent_text
    assert "Robert Williams" in sent_text
    assert "Maria Garcia" in sent_text


@pytest.mark.asyncio
async def test_get_results_as_non_admin(bot, db):
    update = AsyncMock()
    update.effective_user.id = 1
    update.message.text = "1"
    context = MagicMock()
    context.bot.send_message = AsyncMock()
    context.user_data = {"state": UserConversationState.SETTING_POLL_ID_FOR_RESULT}
    cur = db.cursor()
    cur.execute("INSERT INTO polls(id, owner, title) VALUES(1, 124, 'Test Poll')")
    cur.execute("""INSERT INTO votes(poll_id, caster_id, vote, caster_name, timestamp) VALUES
                (1, 456, 1, 'John Doe', 12348),
                (1, 457, 1, 'James Smith', 12345),
                (1, 458, 0, 'Robert Williams', 12346),
                (1, 459, 0, 'Maria Garcia', 12347);""")
    db.commit()

    await bot.message(update, context)

    context.bot.send_message.assert_called_once()
    sent_text = context.bot.send_message.call_args[0][1]
    sent_text = context.bot.send_message.call_args[0][1]
    assert "#1" not in sent_text
    assert "John Doe" not in sent_text
    assert "James Smith" not in sent_text
    assert "Robert Williams" not in sent_text
    assert "Maria Garcia" not in sent_text
