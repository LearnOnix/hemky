"""
Merged Middleman / OGU / Crypto Telegram Bot
=============================================

Runs these three components from ONE Python file/process:
1. Telethon userbot:
   - /mm creates the private middleman group
   - configures permissions/photo
   - invites/promotes OGU + Crypto bots
   - sends/pins the deal template
   - creates an invite link

2. OGU bot:
   - /rec <amount>
   - /ref <amount>
   - /lock <amount>
   - /tos <amount>

3. Crypto bot:
   - watches for CRYPTO_LINK::<invite>
   - replaces the helper message with a clean message
   - watches for "Funds Recieved Successfully" and sends a notification
   - /mute, /unmute, /ban

Environment variables expected in .env:
    API_ID=
    API_HASH=
    PHONE=
    OGU_BOT_TOKEN=
    CRYPTO_BOT_TOKEN=
    ADMIN_USER_ID=123,456
    OGU_BOT_USERNAME=OGUMMdbot
    CRYPTO_BOT_USERNAME=spondscryptobot
    GROUP_PHOTO=group_logo.jpg

Install:
    pip install python-telegram-bot telethon python-dotenv

IMPORTANT:
- Keep .env private.
- Telegram bot tokens/API credentials should be rotated if they were exposed publicly.
"""

from __future__ import annotations

import asyncio
import functools
import logging
import os
from pathlib import Path
from typing import Iterable

from dotenv import load_dotenv

from telegram import ChatPermissions, Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from telethon import TelegramClient, events
from telethon.errors import (
    ChatNotModifiedError,
    FloodWaitError,
    UserAlreadyParticipantError,
)
from telethon.tl.functions.channels import (
    CreateChannelRequest,
    EditAdminRequest,
    EditPhotoRequest,
    InviteToChannelRequest,
    TogglePreHistoryHiddenRequest,
)
from telethon.tl.functions.messages import (
    EditChatDefaultBannedRightsRequest,
    ExportChatInviteRequest,
)
from telethon.tl.types import (
    ChatAdminRights,
    ChatBannedRights,
    InputChatUploadedPhoto,
)


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("merged-middleman")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

load_dotenv()


def required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def parse_admin_ids(raw: str) -> set[int]:
    """
    Supports:
        ADMIN_USER_ID=123456789
        ADMIN_USER_ID=123,456
        ADMIN_USER_ID=123 456
        ADMIN_USER_ID=123;456
    """
    ids: set[int] = set()

    for item in raw.replace(",", " ").replace(";", " ").split():
        try:
            ids.add(int(item))
        except ValueError:
            logger.warning("Ignoring invalid ADMIN_USER_ID value: %r", item)

    if not ids:
        raise RuntimeError(
            "ADMIN_USER_ID must contain at least one valid numeric Telegram user ID."
        )

    return ids


API_ID = int(required_env("API_ID"))
API_HASH = required_env("API_HASH")
PHONE = required_env("PHONE")

OGU_BOT_TOKEN = required_env("OGU_BOT_TOKEN")
CRYPTO_BOT_TOKEN = required_env("CRYPTO_BOT_TOKEN")

ADMIN_IDS = parse_admin_ids(required_env("ADMIN_USER_ID"))

OGU_BOT_USERNAME = os.getenv("OGU_BOT_USERNAME", "OGUMMdbot").strip().lstrip("@")
CRYPTO_BOT_USERNAME = os.getenv(
    "CRYPTO_BOT_USERNAME", "spondscryptobot"
).strip().lstrip("@")

GROUP_PHOTO = os.getenv("GROUP_PHOTO", "group_logo.jpg").strip()


# ---------------------------------------------------------------------------
# Telethon userbot configuration
# ---------------------------------------------------------------------------

client = TelegramClient(
    "mm_userbot_session",
    API_ID,
    API_HASH,
)


MEMBER_RIGHTS = ChatBannedRights(
    until_date=None,
    view_messages=False,
    send_messages=False,
    send_media=False,
    send_stickers=True,
    send_gifs=True,
    send_games=True,
    send_inline=True,
    embed_links=True,
    send_polls=True,
    change_info=True,
    invite_users=True,
    pin_messages=True,
)


ADMIN_RIGHTS = ChatAdminRights(
    change_info=True,
    post_messages=True,
    edit_messages=True,
    delete_messages=True,
    ban_users=True,
    invite_users=True,
    pin_messages=True,
    add_admins=False,
    anonymous=False,
    manage_call=True,
    other=True,
)


FIRST_MESSAGE = """**Please State the deal exactly.**

1. Who is the buyer and seller?
2. What is the deal about?
3. What crypto am i holding ? ( Bitcoin , litecoin , USDT Tether , ERC20 etc )
4. State additional information if necessary."""


# These are assigned during startup. Keeping the references here lets the
# OGU bot and Telethon userbot coordinate directly with the Crypto bot
# without relying on bot-to-bot messages (which Telegram does not reliably
# deliver between bots).
ogu_app: Application | None = None
crypto_app: Application | None = None


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def is_admin(user_id: int | None) -> bool:
    return user_id is not None and user_id in ADMIN_IDS


def admin_only(func):
    """
    Decorator for python-telegram-bot command handlers.
    Unauthorized users are silently ignored, matching the original behavior.
    """
    @functools.wraps(func)
    async def wrapper(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ):
        if not is_admin(update.effective_user.id if update.effective_user else None):
            return
        return await func(update, context)

    return wrapper


async def safe_delete_bot_message(message) -> None:
    try:
        await message.delete()
    except Exception:
        pass


async def reply_and_delete_command(
    update: Update,
    text: str,
) -> None:
    if not update.message:
        return

    await update.message.reply_text(text)
    await safe_delete_bot_message(update.message)


async def promote_with_title(
    entity,
    user,
    rank: str,
    retries: int = 3,
) -> bool:
    for attempt in range(1, retries + 1):
        try:
            await client(
                EditAdminRequest(
                    channel=entity,
                    user_id=user,
                    admin_rights=ADMIN_RIGHTS,
                    rank=rank,
                )
            )
            logger.info("Promoted %s successfully", rank)
            return True

        except FloodWaitError as exc:
            logger.warning(
                "Flood wait while promoting %s: %ss",
                rank,
                exc.seconds,
            )
            await asyncio.sleep(exc.seconds)

        except Exception as exc:
            logger.warning(
                "Promote %s attempt %s/%s failed: %s",
                rank,
                attempt,
                retries,
                exc,
            )
            if attempt < retries:
                await asyncio.sleep(2)

    return False


# ---------------------------------------------------------------------------
# OGU BOT COMMANDS
# ---------------------------------------------------------------------------

@admin_only
async def rec(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await reply_and_delete_command(update, "Usage: /rec <amount>")
        return

    amount = " ".join(context.args)

    text = f"""Funds Recieved Successfully
Total amount - {amount}"""

    if not update.message:
        return

    # Send the OGU response normally.
    await update.message.reply_text(text)

    # Directly notify the Crypto bot from the same Python process.
    # This avoids depending on Telegram delivering one bot's message
    # to another bot.
    if crypto_app is not None:
        try:
            await crypto_app.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Funds Notification message.",
            )
        except Exception as exc:
            logger.exception("Crypto notification failed: %s", exc)

    await safe_delete_bot_message(update.message)


@admin_only
async def ref(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await reply_and_delete_command(update, "Usage: /ref <amount>")
        return

    text = (
        "Please Lock in with the your exact address that the "
        "Middleman Deal was heading with."
    )

    await reply_and_delete_command(update, text)


@admin_only
async def lock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await reply_and_delete_command(update, "Usage: /lock <amount>")
        return

    amount = " ".join(context.args)

    try:
        await context.bot.set_chat_title(
            chat_id=update.effective_chat.id,
            title=f"{amount} | Locked",
        )
    except Exception as exc:
        logger.warning("Title change failed: %s", exc)

    text = "Address have been locked successfully and it is pending for the Verification."

    await reply_and_delete_command(update, text)


@admin_only
async def tos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await reply_and_delete_command(update, "Usage: /tos <amount>")
        return

    amount = " ".join(context.args)

    text = f"""Please send Same {amount} of Crypto to Release the Refund Transaction.

Terms of Service

Refunds will not be provided if the transaction is canceled without mutual confirmation from both the buyer and the seller. If a deal is canceled or time-wasted, the buyer must send the middleman an amount equal to the funds currently held. Once this additional amount has been received, the full held amount will be released within 48 hours through OGU staff support. This security measure is in place to prevent fraudulent refund attempts. If, during the investigation, OGU staff determines that the party requesting a refund was engaging in a scam attempt, the full amount will be permanently withheld.

Reference - t.me/mmtos"""

    await reply_and_delete_command(update, text)


# ---------------------------------------------------------------------------
# CRYPTO BOT COMMANDS
# ---------------------------------------------------------------------------

@admin_only
async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("Reply to a user to mute.")
        return

    user = update.message.reply_to_message.from_user
    if not user:
        await update.message.reply_text("Could not identify the user.")
        return

    try:
        await context.bot.restrict_chat_member(
            chat_id=update.effective_chat.id,
            user_id=user.id,
            permissions=ChatPermissions(can_send_messages=False),
        )
        await update.message.reply_text("User muted.")
    except Exception as exc:
        logger.exception("Mute failed")
        await update.message.reply_text(f"Failed to mute user: {exc}")

    await safe_delete_bot_message(update.message)


@admin_only
async def unmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("Reply to a user to unmute.")
        return

    user = update.message.reply_to_message.from_user
    if not user:
        await update.message.reply_text("Could not identify the user.")
        return

    try:
        await context.bot.restrict_chat_member(
            chat_id=update.effective_chat.id,
            user_id=user.id,
            permissions=ChatPermissions(
                can_send_messages=True,
                can_send_audios=True,
                can_send_documents=True,
                can_send_photos=True,
                can_send_videos=True,
                can_send_video_notes=True,
                can_send_voice_notes=True,
                can_send_polls=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True,
                can_change_info=False,
                can_invite_users=True,
                can_pin_messages=False,
            ),
        )
        await update.message.reply_text("User unmuted.")
    except Exception as exc:
        logger.exception("Unmute failed")
        await update.message.reply_text(f"Failed to unmute user: {exc}")

    await safe_delete_bot_message(update.message)


@admin_only
async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("Reply to a user to ban.")
        return

    user = update.message.reply_to_message.from_user
    if not user:
        await update.message.reply_text("Could not identify the user.")
        return

    try:
        await context.bot.ban_chat_member(
            chat_id=update.effective_chat.id,
            user_id=user.id,
        )
        await update.message.reply_text("User banned.")
    except Exception as exc:
        logger.exception("Ban failed")
        await update.message.reply_text(f"Failed to ban user: {exc}")

    await safe_delete_bot_message(update.message)


# ---------------------------------------------------------------------------
# CRYPTO BOT MESSAGE AUTOMATION
# ---------------------------------------------------------------------------

async def on_crypto_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    msg = update.effective_message

    if not msg or not msg.text:
        return

    text = msg.text

    # Keep this handler for ordinary text sent by users. Bot-to-bot
    # coordination is handled directly by the merged process.
    if text.startswith("CRYPTO_LINK::"):
        # Old helper messages are no longer required in the merged version.
        # If one is encountered, remove it instead of creating duplicate
        # messages.
        await safe_delete_bot_message(msg)
        return

    # This is retained as a fallback for externally generated text matching
    # the old OGU notification format.
    if "Funds Recieved Successfully" in text:
        try:
            await context.bot.send_message(
                chat_id=msg.chat_id,
                text="Funds Notification message.",
            )
        except Exception as exc:
            logger.exception("Failed to send funds notification: %s", exc)


# ---------------------------------------------------------------------------
# USERBOT /mm
# ---------------------------------------------------------------------------

@client.on(events.NewMessage(pattern=r"^/mm(?:@\w+)?$"))
async def mm_handler(event):
    """
    Create and configure a new private middleman group.
    """
    # /mm is a privileged operation because it creates a new group and
    # promotes accounts/bots. Match the admin restriction used by the bots.
    if not is_admin(event.sender_id):
        return

    try:
        # Delete the /mm command immediately.
        try:
            await event.delete()
        except Exception:
            pass

        # 1. Create private megagroup.
        result = await client(
            CreateChannelRequest(
                title="MM Group",
                about="Please Make sure you check the username twice before dealing.",
                megagroup=True,
            )
        )

        group = result.chats[0]
        group_entity = await client.get_entity(group.id)

        logger.info("Group created: %s", group.id)

        # 2. Make history visible.
        try:
            await client(
                TogglePreHistoryHiddenRequest(
                    channel=group_entity,
                    enabled=False,
                )
            )
        except ChatNotModifiedError:
            pass
        except Exception as exc:
            logger.warning("History toggle failed: %s", exc)

        # 3. Set default member permissions.
        try:
            await client(
                EditChatDefaultBannedRightsRequest(
                    peer=group_entity,
                    banned_rights=MEMBER_RIGHTS,
                )
            )
        except Exception as exc:
            logger.warning("Member permissions failed: %s", exc)

        # 4. Group photo.
        photo_path = Path(GROUP_PHOTO)

        if photo_path.exists() and photo_path.is_file():
            try:
                uploaded = await client.upload_file(str(photo_path))

                await client(
                    EditPhotoRequest(
                        channel=group_entity,
                        photo=InputChatUploadedPhoto(uploaded),
                    )
                )

                logger.info("Group photo set")

            except Exception as exc:
                logger.warning("Group photo failed: %s", exc)
        else:
            logger.info("Group photo not found, skipping: %s", photo_path)

        # 5. Get both bot entities.
        ogu = await client.get_entity(OGU_BOT_USERNAME)
        crypto = await client.get_entity(CRYPTO_BOT_USERNAME)

        # 6. Invite bots.
        try:
            await client(
                InviteToChannelRequest(
                    group_entity,
                    [ogu, crypto],
                )
            )
            logger.info("Bots invited")

        except UserAlreadyParticipantError:
            logger.info("One or more bots are already members")

        except Exception as exc:
            logger.warning("Bot invite failed: %s", exc)

        await asyncio.sleep(2)

        # 7. Promote userbot + bots.
        me = await client.get_me()

        await promote_with_title(group_entity, me, "Middleman")
        await promote_with_title(group_entity, ogu, "OGU BOT")
        await promote_with_title(group_entity, crypto, "Crypto BOT")

        await asyncio.sleep(1)

        # 8. Send and pin first deal message.
        msg = await client.send_message(
            group_entity,
            FIRST_MESSAGE,
            parse_mode="md",
        )

        try:
            await client.pin_message(
                group_entity,
                msg,
                notify=False,
            )
            logger.info("First message pinned")
        except Exception as exc:
            logger.warning("Pin failed: %s", exc)

        # 9. Generate real invite link.
        try:
            invite = await client(
                ExportChatInviteRequest(
                    peer=group_entity,
                )
            )

            real_link = invite.link

            # Send the clean invite directly with the Crypto bot.
            # This replaces the old CRYPTO_LINK helper-message mechanism.
            if crypto_app is not None:
                await crypto_app.bot.send_message(
                    chat_id=group.id,
                    text=(
                        "Please forward this link to the next person who "
                        "is involved in the deal.\n\n"
                        f"{real_link}"
                    ),
                )
            else:
                logger.warning("Crypto bot application is not started")

            # Also send the link to the original /mm chat using the
            # user account, preserving the original behavior.
            await client.send_message(
                event.chat_id,
                "Please Join this Group and Send it to the next person "
                "who is involved in the deal.\n\n"
                f"{real_link}",
            )

            logger.info("Invite link created: %s", real_link)

        except Exception as exc:
            logger.exception("Invite link generation failed")
            await client.send_message(
                event.chat_id,
                f"Error while creating invite link: {exc}",
            )

    except FloodWaitError as exc:
        logger.warning("Flood wait: %ss", exc.seconds)
        await client.send_message(
            event.chat_id,
            f"Flood wait – try again in {exc.seconds}s",
        )

    except Exception as exc:
        logger.exception("/mm failed")
        try:
            await client.send_message(
                event.chat_id,
                f"Error: {exc}",
            )
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Python Telegram Bot setup
# ---------------------------------------------------------------------------

def build_ogu_application() -> Application:
    app = Application.builder().token(OGU_BOT_TOKEN).build()

    app.add_handler(CommandHandler("rec", rec))
    app.add_handler(CommandHandler("ref", ref))
    app.add_handler(CommandHandler("lock", lock))
    app.add_handler(CommandHandler("tos", tos))

    return app


def build_crypto_application() -> Application:
    app = Application.builder().token(CRYPTO_BOT_TOKEN).build()

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            on_crypto_message,
        )
    )

    app.add_handler(CommandHandler("mute", mute))
    app.add_handler(CommandHandler("unmute", unmute))
    app.add_handler(CommandHandler("ban", ban))

    return app


async def start_bot_application(app: Application, name: str) -> None:
    """
    Start PTB without run_polling(), because Telethon and both bot
    applications need to share the same asyncio process.
    """
    await app.initialize()
    await app.start()

    if app.updater is None:
        raise RuntimeError(f"{name}: updater is not available")

    await app.updater.start_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )

    logger.info("%s polling started", name)


async def stop_bot_application(app: Application, name: str) -> None:
    if app.updater is not None:
        try:
            await app.updater.stop()
        except Exception:
            logger.exception("%s updater stop failed", name)

    try:
        await app.stop()
    except Exception:
        logger.exception("%s stop failed", name)

    try:
        await app.shutdown()
    except Exception:
        logger.exception("%s shutdown failed", name)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main() -> None:
    global ogu_app, crypto_app

    ogu_app = build_ogu_application()
    crypto_app = build_crypto_application()

    try:
        # Start both bot clients.
        await start_bot_application(ogu_app, "OGU BOT")
        await start_bot_application(crypto_app, "CRYPTO BOT")

        # Start Telethon userbot in the SAME asyncio loop.
        await client.start(phone=PHONE)

        me = await client.get_me()

        logger.info(
            "Userbot logged in as @%s (%s)",
            getattr(me, "username", None),
            getattr(me, "id", None),
        )
        logger.info(
            "Merged system running | admins=%s | OGU=@%s | CRYPTO=@%s",
            sorted(ADMIN_IDS),
            OGU_BOT_USERNAME,
            CRYPTO_BOT_USERNAME,
        )

        # Keep all three clients alive.
        await client.run_until_disconnected()

    finally:
        logger.info("Stopping merged system...")

        if client.is_connected():
            try:
                await client.disconnect()
            except Exception:
                logger.exception("Telethon disconnect failed")

        await stop_bot_application(crypto_app, "CRYPTO BOT")
        await stop_bot_application(ogu_app, "OGU BOT")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Stopped by user")
    except Exception:
        logger.exception("Fatal startup/runtime error")
        raise
