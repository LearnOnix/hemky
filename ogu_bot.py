# ogu_bot.py
import os
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

load_dotenv()
TOKEN = os.getenv("OGU_BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_USER_ID"))

def admin_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id != ADMIN_ID:
            return
        return await func(update, context)
    return wrapper

@admin_only
async def rec(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /rec <amount>")
        return
    amount = " ".join(context.args)
    text = f"""Funds Recieved Successfully 
Total amount - {amount}"""
    await update.message.reply_text(text)
    try:
        await update.message.delete()
    except:
        pass

@admin_only
async def ref(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /ref <amount>")
        return
    text = """Please Lock in with the your exact address that the Middleman Deal was heading with."""
    await update.message.reply_text(text)
    try:
        await update.message.delete()
    except:
        pass

@admin_only
async def lock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /lock <amount>")
        return
    amount = " ".join(context.args)
    try:
        await context.bot.set_chat_title(
            chat_id=update.effective_chat.id,
            title=f"{amount} | Locked"
        )
    except Exception as e:
        print("Title change:", e)

    text = """Address have been locked successfully and it is pending for the Verification."""
    await update.message.reply_text(text)
    try:
        await update.message.delete()
    except:
        pass

@admin_only
async def tos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /tos <amount>")
        return
    amount = " ".join(context.args)
    text = f"""Please send Same {amount} of Crypto to Release the Refund Transaction.

Terms of Service

Refunds will not be provided if the transaction is canceled without mutual confirmation from both the buyer and the seller. If a deal is canceled or time-wasted, the buyer must send the middleman an amount equal to the funds currently held. Once this additional amount has been received, the full held amount will be released within 48 hours through OGU staff support. This security measure is in place to prevent fraudulent refund attempts. If, during the investigation, OGU staff determines that the party requesting a refund was engaging in a scam attempt, the full amount will be permanently withheld.

Reference - t.me/mmtos"""
    await update.message.reply_text(text)
    try:
        await update.message.delete()
    except:
        pass
    
def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("rec", rec))
    app.add_handler(CommandHandler("ref", ref))
    app.add_handler(CommandHandler("lock", lock))
    app.add_handler(CommandHandler("tos", tos))
    print("OGU BOT running…")
    app.run_polling()

if __name__ == "__main__":
    main()
