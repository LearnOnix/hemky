# crypto_bot.py
import os
from dotenv import load_dotenv
from telegram import Update, ChatPermissions
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ContextTypes, filters
)

load_dotenv()
TOKEN = os.getenv("CRYPTO_BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_USER_ID"))

def admin_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id != ADMIN_ID:
            return
        return await func(update, context)
    return wrapper

async def on_new_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg or not msg.text:
        return

    # Detect helper message from userbot containing the real invite link
    if msg.text.startswith("CRYPTO_LINK::"):
        real_link = msg.text.split("CRYPTO_LINK::", 1)[1].strip()

        # Delete the helper message
        try:
            await msg.delete()
        except:
            pass

        # Send clean separate message (not a reply)
        text = f"""Please forward this link to the next person who is involved in the deal.

{real_link}"""
        await context.bot.send_message(
            chat_id=msg.chat_id,
            text=text
        )
        return

    # After OGU /rec
    if "Funds Recieved Successfully" in msg.text:
        await context.bot.send_message(
            chat_id=msg.chat_id,
            text="Funds Notification message."
        )

@admin_only
async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("Reply to a user to mute.")
        return
    user_id = update.message.reply_to_message.from_user.id
    await context.bot.restrict_chat_member(
        chat_id=update.effective_chat.id,
        user_id=user_id,
        permissions=ChatPermissions(can_send_messages=False)
    )
    await update.message.reply_text("User muted.")
    try:
        await update.message.delete()
    except:
        pass

@admin_only
async def unmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("Reply to a user to unmute.")
        return
    user_id = update.message.reply_to_message.from_user.id
    await context.bot.restrict_chat_member(
        chat_id=update.effective_chat.id,
        user_id=user_id,
        permissions=ChatPermissions(
            can_send_messages=True,
            can_send_media_messages=True,
            can_send_other_messages=False,
            can_add_web_page_previews=False
        )
    )
    await update.message.reply_text("User unmuted.")
    try:
        await update.message.delete()
    except:
        pass

@admin_only
async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("Reply to a user to ban.")
        return
    user_id = update.message.reply_to_message.from_user.id
    await context.bot.ban_chat_member(update.effective_chat.id, user_id)
    await update.message.reply_text("User banned.")
    try:
        await update.message.delete()
    except:
        pass

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_new_message))
    app.add_handler(CommandHandler("mute", mute))
    app.add_handler(CommandHandler("unmute", unmute))
    app.add_handler(CommandHandler("ban", ban))
    print("Crypto Tracker BOT running…")
    app.run_polling()

if __name__ == "__main__":
    main()
