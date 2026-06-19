from __future__ import annotations

import logging
from typing import Final

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import Forbidden, TelegramError
from telegram.ext import (
    Application,
    ApplicationBuilder,
    ChatJoinRequestHandler,
    CommandHandler,
    ContextTypes,
)

from .config import Settings, load_settings
from .db import Database

logging.basicConfig(
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)
DB_KEY: Final[str] = "db"
SETTINGS_KEY: Final[str] = "settings"


def is_admin(user_id: int | None, settings: Settings) -> bool:
    return user_id is not None and user_id in settings.admin_user_ids


async def post_init(application: Application) -> None:
    db: Database = application.bot_data[DB_KEY]
    await db.init()
    logger.info("Database initialized")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.application.bot_data[SETTINGS_KEY]
    db: Database = context.application.bot_data[DB_KEY]
    user = update.effective_user
    if user:
        await db.upsert_user(
            user_id=user.id,
            user_chat_id=update.effective_chat.id if update.effective_chat else None,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
            bot_started=True,
        )
    payload = context.args[0] if context.args else None
    text = (
        "JoinBridge Bot active hai. Jab aap join request bhejte ho, source channel/group ka latest configured post yahan receive ho sakta hai."
    )
    if payload:
        text += f"\n\nSource token: {payload}"
    await update.effective_message.reply_text(text)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        "/start\n"
        "/help\n"
        "/bind\n"
        "/setmode copy|forward\n"
        "/setlatest (reply to a source post)\n"
        "/stats\n"
        "/chatstats <chat_id>\n"
        "/broadcast <message>"
    )


async def bind_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.application.bot_data[SETTINGS_KEY]
    db: Database = context.application.bot_data[DB_KEY]
    user = update.effective_user
    chat = update.effective_chat
    if not is_admin(user.id if user else None, settings):
        await update.effective_message.reply_text("Not allowed.")
        return
    if not chat:
        return
    await db.upsert_source_chat(chat.id, chat.title or str(chat.id), getattr(chat, "username", None), settings.default_delivery_mode)
    await update.effective_message.reply_text(f"Bound: {chat.title or chat.id}")


async def set_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.application.bot_data[SETTINGS_KEY]
    db: Database = context.application.bot_data[DB_KEY]
    user = update.effective_user
    chat = update.effective_chat
    if not is_admin(user.id if user else None, settings):
        await update.effective_message.reply_text("Not allowed.")
        return
    if not chat:
        return
    if not context.args or context.args[0].lower() not in {"copy", "forward"}:
        await update.effective_message.reply_text("Usage: /setmode copy|forward")
        return
    mode = context.args[0].lower()
    await db.upsert_source_chat(chat.id, chat.title or str(chat.id), getattr(chat, "username", None), mode)
    await db.set_delivery_mode(chat.id, mode)
    await update.effective_message.reply_text(f"Delivery mode set to {mode}")


async def set_latest(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.application.bot_data[SETTINGS_KEY]
    db: Database = context.application.bot_data[DB_KEY]
    user = update.effective_user
    chat = update.effective_chat
    message = update.effective_message
    if not is_admin(user.id if user else None, settings):
        await message.reply_text("Not allowed.")
        return
    if not chat or not message:
        return
    if not message.reply_to_message:
        await message.reply_text("Reply to the source post with /setlatest")
        return
    await db.upsert_source_chat(chat.id, chat.title or str(chat.id), getattr(chat, "username", None), settings.default_delivery_mode)
    note = message.reply_to_message.caption or message.reply_to_message.text
    await db.set_latest_message(chat.id, chat.id, message.reply_to_message.message_id, note)
    await message.reply_text(f"Latest post saved: message_id={message.reply_to_message.message_id}")


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.application.bot_data[SETTINGS_KEY]
    db: Database = context.application.bot_data[DB_KEY]
    user = update.effective_user
    if not is_admin(user.id if user else None, settings):
        await update.effective_message.reply_text("Not allowed.")
        return
    s = await db.get_global_stats()
    await update.effective_message.reply_text(
        "Global stats\n"
        f"Source chats: {s['total_source_chats']}\n"
        f"Total users: {s['total_users']}\n"
        f"Active users: {s['active_users']}\n"
        f"Total joins: {s['total_joins']}\n"
        f"Delivered DMs: {s['delivered_dms']}\n"
        f"Approved joins: {s['approved_joins']}"
    )


async def chat_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.application.bot_data[SETTINGS_KEY]
    db: Database = context.application.bot_data[DB_KEY]
    user = update.effective_user
    if not is_admin(user.id if user else None, settings):
        await update.effective_message.reply_text("Not allowed.")
        return
    if not context.args:
        await update.effective_message.reply_text("Usage: /chatstats <chat_id>")
        return
    chat_id = int(context.args[0])
    s = await db.get_chat_stats(chat_id)
    if not s:
        await update.effective_message.reply_text("Chat not found")
        return
    await update.effective_message.reply_text(
        f"Chat: {s['title']}\n"
        f"Mode: {s['delivery_mode']}\n"
        f"Latest message id: {s['latest_message_id']}\n"
        f"Joins: {s['joins']}\n"
        f"Delivered: {s['delivered']}\n"
        f"Approved: {s['approved']}"
    )


async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.application.bot_data[SETTINGS_KEY]
    db: Database = context.application.bot_data[DB_KEY]
    user = update.effective_user
    if not is_admin(user.id if user else None, settings):
        await update.effective_message.reply_text("Not allowed.")
        return
    if not context.args:
        await update.effective_message.reply_text("Usage: /broadcast <message>")
        return
    text = update.effective_message.text.partition(" ")[2].strip()
    targets = await db.get_broadcast_targets()
    sent_count = 0
    failed_count = 0
    for row in targets:
        try:
            await context.bot.send_message(chat_id=row["user_chat_id"], text=text)
            sent_count += 1
        except Forbidden:
            failed_count += 1
            await db.mark_blocked(row["user_id"])
        except TelegramError:
            failed_count += 1
    await db.log_broadcast(user.id, text, sent_count, failed_count)
    await update.effective_message.reply_text(f"Broadcast done. Sent={sent_count}, Failed={failed_count}")


async def handle_join_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.application.bot_data[SETTINGS_KEY]
    db: Database = context.application.bot_data[DB_KEY]
    req = update.chat_join_request
    if not req:
        return

    source_chat = req.chat
    user = req.from_user
    await db.upsert_source_chat(source_chat.id, source_chat.title or str(source_chat.id), getattr(source_chat, "username", None), settings.default_delivery_mode)
    await db.upsert_user(
        user_id=user.id,
        user_chat_id=req.user_chat_id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        bot_started=False,
    )

    chat_cfg = await db.get_source_chat(source_chat.id)
    dm_status = "failed"
    approval_status = "pending"
    sent_message_id = None

    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("Open Bot", url=f"https://t.me/{settings.bot_username}?start=jr_{source_chat.id}")]]
    )

    try:
        if chat_cfg and chat_cfg["latest_message_id"] and chat_cfg["latest_message_chat_id"]:
            if chat_cfg["delivery_mode"] == "forward":
                msg = await context.bot.forward_message(
                    chat_id=req.user_chat_id,
                    from_chat_id=chat_cfg["latest_message_chat_id"],
                    message_id=chat_cfg["latest_message_id"],
                )
            else:
                msg = await context.bot.copy_message(
                    chat_id=req.user_chat_id,
                    from_chat_id=chat_cfg["latest_message_chat_id"],
                    message_id=chat_cfg["latest_message_id"],
                )
            sent_message_id = getattr(msg, "message_id", None)
            await context.bot.send_message(
                chat_id=req.user_chat_id,
                text=f"{source_chat.title} se latest update bhej diya gaya hai. Neeche button se bot open karo.",
                reply_markup=keyboard,
            )
        else:
            msg = await context.bot.send_message(
                chat_id=req.user_chat_id,
                text=f"Aapki join request {source_chat.title} ke liye receive ho gayi hai. Bot open karne ke liye button use karo.",
                reply_markup=keyboard,
            )
            sent_message_id = msg.message_id
        dm_status = "sent"

        if settings.auto_approve:
            await req.approve()
            approval_status = "approved"
    except Forbidden:
        dm_status = "blocked"
        await db.mark_blocked(user.id)
    except TelegramError as exc:
        logger.warning("Join DM failed for user=%s chat=%s error=%s", user.id, source_chat.id, exc)

    await db.log_join_event(
        source_chat_id=source_chat.id,
        user_id=user.id,
        user_chat_id=req.user_chat_id,
        dm_status=dm_status,
        approval_status=approval_status,
        message_id_sent=sent_message_id,
    )


def build_application() -> Application:
    settings = load_settings()
    db = Database(settings.database_path)
    app = ApplicationBuilder().token(settings.bot_token).post_init(post_init).build()
    app.bot_data[DB_KEY] = db
    app.bot_data[SETTINGS_KEY] = settings

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("bind", bind_chat))
    app.add_handler(CommandHandler("setmode", set_mode))
    app.add_handler(CommandHandler("setlatest", set_latest))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("chatstats", chat_stats))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(ChatJoinRequestHandler(handle_join_request))
    return app


def main() -> None:
    application = build_application()
    application.run_polling(allowed_updates=Update.ALL_TYPES)
