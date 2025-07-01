# pyrogram imports
from pyrogram import Client, filters
from pyrogram.enums import MessageMediaType
from pyrogram.errors import FloodWait
from pyrogram.file_id import FileId
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ForceReply

# hachoir imports
from hachoir.metadata import extractMetadata
from hachoir.parser import createParser
from PIL import Image

# bots imports
from helper.utils import progress_for_pyrogram, convert, humanbytes, add_prefix_suffix, remove_path
from helper.database import digital_botz
from helper.ffmpeg import change_metadata
from config import Config

# extra imports
from asyncio import sleep
import os, time, asyncio, logging, shutil
import ffmpeg

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

UPLOAD_TEXT = """Uploading Started...."""
DOWNLOAD_TEXT = """Download Started..."""
DEFAULT_LIMIT = 4000000000  # 4GB as fallback

app = Client("4gb_FileRenameBot", api_id=Config.API_ID, api_hash=Config.API_HASH, session_string=Config.STRING_SESSION)

@Client.on_message(filters.private & (filters.audio | filters.document | filters.video))
async def rename_start(client, message):
    user_id = message.from_user.id
    rkn_file = getattr(message, message.media.value)
    filename = rkn_file.file_name
    filesize = humanbytes(rkn_file.file_size)
    mime_type = rkn_file.mime_type
    dcid = FileId.decode(rkn_file.file_id).dc_id
    extension_type = mime_type.split('/')[0]

    try:
        if client.premium and client.uploadlimit:
            await digital_botz.reset_uploadlimit_access(user_id)
            user_data = await digital_botz.get_user_data(user_id)
            limit = user_data.get('uploadlimit', DEFAULT_LIMIT)
            used = user_data.get('used_limit', 0)
            
            logger.info(f"User ID: {user_id}, Used: {used}, Limit: {limit}")

            if int(limit) == 0:
                used_percentage = 0
                logger.warning(f"Limit is zero for user {user_id}, setting used_percentage to 0")
            else:
                used_percentage = (int(used) / int(limit)) * 100

            remain = int(limit) - int(used)
            if remain < int(rkn_file.file_size):
                return await message.reply_text(
                    f"{used_percentage:.2f}% Of Daily Upload Limit {humanbytes(limit)}.\n\n"
                    f"Media Size: {filesize}\nYour Used Daily Limit {humanbytes(used)}\n\n"
                    f"You have only **{humanbytes(remain)}** Data.\nPlease, Buy Premium Plan.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🪪 Uᴘɢʀᴀᴅᴇ", callback_data="plans")]])
                )

        reply_text = (
            f"**__ᴍᴇᴅɪᴀ ɪɴꜰᴏ:\n\n"
            f"◈ ᴏʟᴅ ꜰɪʟᴇ ɴᴀᴍᴇ: `{filename}`\n\n"
            f"◈ ᴇxᴛᴇɴsɪᴏɴ: `{extension_type.upper()}`\n"
            f"◈ ꜰɪʟᴇ ꜱɪᴢᴇ: `{filesize}`\n"
            f"◈ ᴍɪᴍᴇ ᴛʏᴇᴩ: `{mime_type}`\n"
            f"◈ ᴅᴄ ɪᴅ: `{dcid}`\n\n"
            f"ᴘʟᴇᴀsᴇ ᴇɴᴛᴇʀ ᴛʜᴇ ɴᴇᴡ ғɪʟᴇɴᴀᴍᴇ ᴡɪᴛʜ ᴇxᴛᴇɴsɪᴏɴ ᴀɴᴅ ʀᴇᴘʟʏ ᴛʜɪs ᴍᴇssᴀɢᴇ....__**"
        )

        if await digital_botz.has_premium_access(user_id) and client.premium:
            if not Config.STRING_SESSION and rkn_file.file_size > 2000 * 1024 * 1024:
                return await message.reply_text("Sᴏʀʀy Bʀᴏ Tʜɪꜱ Bᴏᴛ Iꜱ Dᴏᴇꜱɴ'ᴛ Sᴜᴩᴩᴏʀᴛ Uᴩʟᴏᴀᴅɪɴɢ Fɪʟᴇꜱ Bɪɢɢᴇʀ Tʜᴀɴ 2Gʙ+")
        else:
            if rkn_file.file_size > 2000 * 1024 * 1024 and client.premium:
                return await message.reply_text("If you want to rename 4GB+ files then you will have to buy premium. /plans")

        try:
            await message.reply_text(
                text=reply_text,
                reply_to_message_id=message.id,
                reply_markup=ForceReply(True)
            )
            await sleep(30)
        except FloodWait as e:
            await sleep(e.value)
            await message.reply_text(
                text=reply_text,
                reply_to_message_id=message.id,
                reply_markup=ForceReply(True)
            )
        except Exception as e:
            logger.error(f"Error sending reply message: {str(e)}")
            pass

    except Exception as e:
        logger.error(f"Error in rename_start: {str(e)}")
        await message.reply_text(f"An error occurred: {str(e)}")

@Client.on_message(filters.private & filters.reply)
async def refunc(client, message):
    reply_message = message.reply_to_message
    if (reply_message.reply_markup) and isinstance(reply_message.reply_markup, ForceReply):
        new_name = message.text
        await message.delete()
        msg = await client.get_messages(message.chat.id, reply_message.id)
        file = msg.reply_to_message
        media = getattr(file, file.media.value)
        if not "." in new_name:
            if "." in media.file_name:
                extn = media.file_name.rsplit('.', 1)[-1]
            else:
                extn = "mkv"
            new_name = new_name + "." + extn
        await reply_message.delete()

        button = [[InlineKeyboardButton("📁 Dᴏᴄᴜᴍᴇɴᴛ", callback_data="upload_document")]]
        if file.media in [MessageMediaType.VIDEO, MessageMediaType.DOCUMENT]:
            button.append([InlineKeyboardButton("🎥 Vɪᴅᴇᴏ", callback_data="upload_video")])
        elif file.media == MessageMediaType.AUDIO:
            button.append([InlineKeyboardButton("🎵 Aᴜᴅɪᴏ", callback_data="upload_audio")])
        await message.reply(
            text=f"**Sᴇʟᴇᴄᴛ Tʜᴇ Oᴜᴛᴩᴜᴛ Fɪʟᴇ Tyᴩᴇ**\n**• Fɪʟᴇ Nᴀᴍᴇ :-**`{new_name}`",
            reply_to_message_id=file.id,
            reply_markup=InlineKeyboardMarkup(button)
        )

@Client.on_callback_query(filters.regex("upload"))
async def doc(bot, update):
    rkn_processing = await update.message.edit("`Processing...`")

    # Creating Directory for Metadata
    if not os.path.isdir("Metadata"):
        os.mkdir("Metadata")
    if not os.path.isdir("Renames"):
        os.mkdir("Renames")

    # Check disk space
    total, used, free = shutil.disk_usage("/")
    if free < 2000000000:  # 2GB free space required
        return await rkn_processing.edit("⚠️ Not enough disk space. Upgrade to Performance dyno.")

    user_id = int(update.message.chat.id)
    new_name = update.message.text
    new_filename_ = new_name.split(":-")[1].strip()
    user_data = await digital_botz.get_user_data(user_id)

    try:
        # Adding prefix and suffix
        prefix = await digital_botz.get_prefix(user_id)
        suffix = await digital_botz.get_suffix(user_id)
        new_filename = add_prefix_suffix(new_filename_, prefix, suffix)
    except Exception as e:
        logger.error(f"Error adding prefix/suffix: {str(e)}")
        return await rkn_processing.edit(
            f"⚠️ Something went wrong can't able to set Prefix or Suffix ☹️ \n\n"
            f"❄️ Contact My Creator -> @Baii_Ji\nError: {e}"
        )

    # msg file location
    file = update.message.reply_to_message
    media = getattr(file, file.media.value)

    # file downloaded path
    file_path = f"Renames/{new_filename}"
    metadata_path = f"Metadata/{new_filename}"

    await rkn_processing.edit("`Try To Download....`")
    if bot.premium and bot.uploadlimit:
        limit = user_data.get('uploadlimit', DEFAULT_LIMIT)
        used = user_data.get('used_limit', 0)
        await digital_botz.set_used_limit(user_id, media.file_size)
        total_used = int(used) + int(media.file_size)
        await digital_botz.set_used_limit(user_id, total_used)

    # Parallel download and metadata prep
    async def download_file():
        return await bot.download_media(
            message=file,
            file_name=file_path,
            progress=progress_for_pyrogram,
            progress_args=(DOWNLOAD_TEXT, rkn_processing, time.time())
        )

    async def prepare_metadata():
        if await digital_botz.get_metadata_mode(user_id):
            metadata = await digital_botz.get_metadata_code(user_id)
            if metadata and change_metadata(file_path, metadata_path, metadata):
                return metadata_path
        return file_path

    try:
        download_task = asyncio.create_task(download_file())
        metadata_task = asyncio.create_task(prepare_metadata())
        dl_path = await download_task
        final_path = await metadata_task
    except Exception as e:
        if bot.premium and bot.uploadlimit:
            used_remove = int(used) - int(media.file_size)
            await digital_botz.set_used_limit(user_id, used_remove)
        logger.error(f"Download or metadata error: {str(e)}")
        return await rkn_processing.edit(f"Error: {e}")

    await rkn_processing.edit("`Try To Uploading....`") if not await digital_botz.get_metadata_mode(user_id) else await rkn_processing.edit("**Metadata added to the file successfully ✅**\n\n**Tʀyɪɴɢ Tᴏ Uᴩʟᴏᴀᴅɪɴɢ....**")

    # Generate 1-minute sample video if enabled
    sample_path = None
    enable_sample = os.getenv("ENABLE_SAMPLE_VIDEO", "True").lower() == "true"
    if enable_sample and file.media == MessageMediaType.VIDEO:
        try:
            sample_filename = f"Renames/sample_{new_filename}"
            ffmpeg.input(final_path, ss=0, t=60).output(sample_filename, vcodec='copy', acodec='copy', loglevel="quiet").run()
            sample_path = sample_filename
            await rkn_processing.edit("`Sample video generated, uploading now...`")
        except Exception as e:
            logger.error(f"Sample video generation error: {str(e)}")
            sample_path = None

    duration = 0
    try:
        parser = createParser(final_path)
        if parser:
            metadata = extractMetadata(parser)
            if metadata and metadata.has("duration"):
                duration = metadata.get('duration').seconds
            parser.close()
    except Exception as e:
        logger.error(f"Metadata extraction error: {str(e)}")

    ph_path = None
    c_caption = await digital_botz.get_caption(user_id)
    c_thumb = await digital_botz.get_thumbnail(user_id)

    if c_caption:
        try:
            caption = c_caption.format(filename=new_filename, filesize=humanbytes(media.file_size), duration=convert(duration))
        except Exception as e:
            if bot.premium and bot.uploadlimit:
                used_remove = int(used) - int(media.file_size)
                await digital_botz.set_used_limit(user_id, used_remove)
            logger.error(f"Caption error: {str(e)}")
            return await rkn_processing.edit(f"Yᴏᴜʀ Cᴀᴩᴛɪᴏɴ Eʀʀᴏʀ Exᴄᴇᴩᴛ Kᴇyᴡᴏʀᴅ Aʀɢᴜᴍᴇɴᴛ ●> ({e})")
    else:
        caption = f"**{new_filename}**"

    if media.thumbs or c_thumb:
        try:
            if c_thumb:
                ph_path = await bot.download_media(c_thumb)
            else:
                ph_path = await bot.download_media(media.thumbs[0].file_id)
            Image.open(ph_path).convert("RGB").save(ph_path)
            img = Image.open(ph_path)
            img.resize((320, 320))
            img.save(ph_path, "JPEG")
        except Exception as e:
            logger.error(f"Thumbnail processing error: {str(e)}")
            ph_path = None

    type = update.data.split("_")[1]
    async def send_with_retry(method, *args, retries=3, **kwargs):
        for i in range(retries):
            try:
                return await method(*args, **kwargs)
            except ConnectionResetError:
                if i == retries - 1:
                    raise
                await asyncio.sleep(2 ** i)

    try:
        if media.file_size > 2000 * 1024 * 1024:
            if type == "document":
                filw = await send_with_retry(app.send_document, Config.LOG_CHANNEL, document=final_path, thumb=ph_path, caption=caption, progress=progress_for_pyrogram, progress_args=(UPLOAD_TEXT, rkn_processing, time.time()))
                if sample_path:
                    await send_with_retry(app.send_document, Config.LOG_CHANNEL, document=sample_path, thumb=ph_path, caption=f"Sample - {caption}", progress=progress_for_pyrogram, progress_args=(UPLOAD_TEXT, rkn_processing, time.time()))
            elif type == "video":
                filw = await send_with_retry(app.send_video, Config.LOG_CHANNEL, video=final_path, caption=caption, thumb=ph_path, duration=duration, progress=progress_for_pyrogram, progress_args=(UPLOAD_TEXT, rkn_processing, time.time()))
                if sample_path:
                    await send_with_retry(app.send_video, Config.LOG_CHANNEL, video=sample_path, caption=f"Sample - {caption}", thumb=ph_path, duration=60, progress=progress_for_pyrogram, progress_args=(UPLOAD_TEXT, rkn_processing, time.time()))
            elif type == "audio":
                filw = await send_with_retry(app.send_audio, Config.LOG_CHANNEL, audio=final_path, caption=caption, thumb=ph_path, duration=duration, progress=progress_for_pyrogram, progress_args=(UPLOAD_TEXT, rkn_processing, time.time()))
                if sample_path:
                    await send_with_retry(app.send_audio, Config.LOG_CHANNEL, audio=sample_path, caption=f"Sample - {caption}", thumb=ph_path, duration=60, progress=progress_for_pyrogram, progress_args=(UPLOAD_TEXT, rkn_processing, time.time()))
            from_chat = filw.chat.id
            mg_id = filw.id
            await sleep(2)
            await bot.copy_message(update.from_user.id, from_chat, mg_id)
            await bot.delete_messages(from_chat, mg_id)
        else:
            if type == "document":
                await bot.send_document(update.message.chat.id, document=final_path, thumb=ph_path, caption=caption, progress=progress_for_pyrogram, progress_args=(UPLOAD_TEXT, rkn_processing, time.time()))
                if sample_path:
                    await bot.send_document(update.message.chat.id, document=sample_path, thumb=ph_path, caption=f"Sample - {caption}", progress=progress_for_pyrogram, progress_args=(UPLOAD_TEXT, rkn_processing, time.time()))
            elif type == "video":
                await bot.send_video(update.message.chat.id, video=final_path, caption=caption, thumb=ph_path, duration=duration, progress=progress_for_pyrogram, progress_args=(UPLOAD_TEXT, rkn_processing, time.time()))
                if sample_path:
                    await bot.send_video(update.message.chat.id, video=sample_path, caption=f"Sample - {caption}", thumb=ph_path, duration=60, progress=progress_for_pyrogram, progress_args=(UPLOAD_TEXT, rkn_processing, time.time()))
            elif type == "audio":
                await bot.send_audio(update.message.chat.id, audio=final_path, caption=caption, thumb=ph_path, duration=duration, progress=progress_for_pyrogram, progress_args=(UPLOAD_TEXT, rkn_processing, time.time()))
                if sample_path:
                    await bot.send_audio(update.message.chat.id, audio=sample_path, caption=f"Sample - {caption}", thumb=ph_path, duration=60, progress=progress_for_pyrogram, progress_args=(UPLOAD_TEXT, rkn_processing, time.time()))
    except Exception as e:
        if bot.premium and bot.uploadlimit:
            used_remove = int(used) - int(media.file_size)
            await digital_botz.set_used_limit(user_id, used_remove)
        logger.error(f"Upload error: {str(e)}")
        await remove_path(ph_path, file_path, dl_path, metadata_path, sample_path)
        return await rkn_processing.edit(f"Eʀʀᴏʀ {e}")

    await remove_path(ph_path, file_path, dl_path, metadata_path, sample_path)
    return await rkn_processing.edit("Uploaded Successfully....")

# please give credit 🙏🥲
