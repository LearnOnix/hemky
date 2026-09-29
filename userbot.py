# userbot.py
import asyncio
asyncio.set_event_loop(asyncio.new_event_loop())

import os
from dotenv import load_dotenv
from telethon import TelegramClient, events
from telethon.tl.functions.channels import (
    CreateChannelRequest, EditAdminRequest, InviteToChannelRequest,
    TogglePreHistoryHiddenRequest, EditPhotoRequest
)
from telethon.tl.functions.messages import EditChatDefaultBannedRightsRequest, ExportChatInviteRequest
from telethon.tl.types import (
    ChatAdminRights, ChatBannedRights, InputChatUploadedPhoto
)
from telethon.errors import ChatNotModifiedError, FloodWaitError, UserAlreadyParticipantError

load_dotenv()

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
PHONE = os.getenv("PHONE")
OGU_BOT_USERNAME = os.getenv("OGU_BOT_USERNAME")
CRYPTO_BOT_USERNAME = os.getenv("CRYPTO_BOT_USERNAME")
GROUP_PHOTO = os.getenv("GROUP_PHOTO", "group_logo.jpg")

client = TelegramClient("mm_userbot_session", API_ID, API_HASH)

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

async def promote_with_title(entity, user, rank, retries=3):
    for i in range(retries):
        try:
            await client(EditAdminRequest(
                channel=entity,
                user_id=user,
                admin_rights=ADMIN_RIGHTS,
                rank=rank
            ))
            print(f"Promoted {rank} successfully")
            return True
        except Exception as e:
            print(f"Promote {rank} attempt {i+1} failed: {e}")
            await asyncio.sleep(2)
    return False

@client.on(events.NewMessage(pattern=r'^/mm(?:@\w+)?$'))
async def mm_handler(event):
    try:
        # Delete the /mm command immediately
        try:
            await event.delete()
        except:
            pass

        # 1. Create private megagroup
        result = await client(CreateChannelRequest(
            title="MM Group",
            about="Please Make sure you check the username twice before dealing.",
            megagroup=True
        ))
        group = result.chats[0]
        group_entity = await client.get_entity(group.id)
        print(f"Group created: {group.id}")

        # 2. History visible (safe)
        try:
            await client(TogglePreHistoryHiddenRequest(channel=group_entity, enabled=False))
        except ChatNotModifiedError:
            pass
        except Exception as e:
            print(f"History toggle: {e}")

        # 3. Member permissions
        try:
            await client(EditChatDefaultBannedRightsRequest(
                peer=group_entity,
                banned_rights=MEMBER_RIGHTS
            ))
        except Exception as e:
            print(f"Permissions: {e}")

        # 4. Group photo
        if os.path.exists(GROUP_PHOTO):
            try:
                uploaded = await client.upload_file(GROUP_PHOTO)
                await client(EditPhotoRequest(
                    channel=group_entity,
                    photo=InputChatUploadedPhoto(uploaded)
                ))
                print("Photo set")
            except Exception as e:
                print(f"Photo: {e}")

        # 5. Invite bots
        ogu = await client.get_entity(OGU_BOT_USERNAME)
        crypto = await client.get_entity(CRYPTO_BOT_USERNAME)

        try:
            await client(InviteToChannelRequest(group_entity, [ogu, crypto]))
            print("Bots invited")
        except UserAlreadyParticipantError:
            pass
        except Exception as e:
            print(f"Invite: {e}")

        await asyncio.sleep(2)

        # 6. Promote with titles
        me = await client.get_me()
        await promote_with_title(group_entity, me, "Middleman")
        await promote_with_title(group_entity, ogu, "OGU BOT")
        await promote_with_title(group_entity, crypto, "Crypto BOT")

        await asyncio.sleep(1)

        # 7. Send + pin first message
        msg = await client.send_message(group_entity, FIRST_MESSAGE, parse_mode="md")
        await client.pin_message(group_entity, msg, notify=False)
        print("First message pinned")

        # 8. Generate real invite link and notify Crypto Tracker
        try:
            invite = await client(ExportChatInviteRequest(peer=group_entity))
            real_link = invite.link

            # Temporary helper message for Crypto Tracker
            await client.send_message(
                group_entity,
                f"CRYPTO_LINK::{real_link}"
            )

            # Success message in original chat
            await client.send_message(
                event.chat_id,
                f"Please Join this Group and Send it to the next person who is involved in the deal.\n\n"
                f"{real_link}"
            )
        except Exception as e:
            print(f"Invite link: {e}")

    except FloodWaitError as e:
        await client.send_message(event.chat_id, f"Flood wait – try again in {e.seconds}s")
    except Exception as e:
        await client.send_message(event.chat_id, f"Error: {e}")
        print(f"Full error: {e}")

async def main():
    await client.start(phone=PHONE)
    print("Userbot running (final)…")
    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
