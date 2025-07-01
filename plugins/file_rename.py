from pyrogram import Client, filters
from pyrogram.enums import MessageMediaType
from pyrogram.errors import FloodWait
from pyrogram.file_id import FileId
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ForceReply
from hachoir.metadata import extractMetadata
from hachoir.parser import createParser
from PIL import Image
from helper.utils import progress_for_pyrogram, convert, humanbytes, add_prefix_suffix
from helper.database import digital_botz
from helper.ffmpeg import change_metadata
from config import Config
from asyncio import sleep
import os, time, asyncio, logging, shutil
import ffmpeg

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

UPLOAD_TEXT = "Uploading Started...."
DOWNLOAD_TEXT = "Download Started..."
DEFAULT_LIMIT = 4000000000

app = Client("4gb_FileRenameBot", api_id=Config.API_ID, api_hash=Config.API_HASH, session_string=Config.STRING_SESSION)

async def remove_path(*paths):
    for path in paths:
        try:
            if path and os.path.exists(path):
                if os.path.isdir(path):
                    shutil.rmtree(path, ignore_errors=True)
                else:
                    os.remove(path)
        except Exception as e:
            logger.warning(f"Failed to remove {path}: {e}")

@app.on_message(filters.private & (filters.audio | filters.document | filters.video))
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
            used_percentage = (int(used) / int(limit)) * 100 if int(limit) != 0 else 0
            remain = int(limit) - int(used)
            if remain < int(rkn_file.file_size):
                return await message.reply_text(
                    f"{used_percentage:.2f}% of {humanbytes(limit)} limit used.\n"
                    f"Media Size: {filesize}\nUsed: {humanbytes(used)}\nRemaining: {humanbytes(remain)}",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Upgrade", callback_data="plans")]])
                )

        if await digital_botz.has_premium_access(user_id) and client.premium:
            if not Config.STRING_SESSION and rkn_file.file_size > 2000 * 1024 * 1024:
                return await message.reply_text("Cannot rename files > 2GB without string session.")
        elif rkn_file.file_size > 2000 * 1024 * 1024:
            return await message.reply_text("Buy premium to rename 4GB+ files. /plans")

        reply_text = f"**File Info:**\n`{filename}`\nSize: {filesize}\nType: {extension_type}"
        await message.reply_text(reply_text, reply_to_message_id=message.id, reply_markup=ForceReply(True))
        await sleep(30)
    except FloodWait as e:
        await sleep(e.value)
        await message.reply_text(reply_text, reply_to_message_id=message.id, reply_markup=ForceReply(True))
    except Exception as e:
        logger.error(f"rename_start error: {e}")
        await message.reply_text(f"Error: {e}")

@app.on_message(filters.private & filters.reply)
async def refunc(client, message):
    if message.reply_to_message.reply_markup and isinstance(message.reply_to_message.reply_markup, ForceReply):
        new_name = message.text
        await message.delete()
        file = message.reply_to_message.reply_to_message
        media = getattr(file, file.media.value)
        extn = media.file_name.rsplit('.', 1)[-1] if '.' in media.file_name else "mkv"
        if '.' not in new_name:
            new_name += f".{extn}"
        await message.reply_text(
            f"Select Output Type for `{new_name}`",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📁 Document", callback_data="upload_document")],
                [InlineKeyboardButton("🎥 Video", callback_data="upload_video")],
                [InlineKeyboardButton("🎵 Audio", callback_data="upload_audio")]
            ]),
            reply_to_message_id=file.id
        )

@app.on_callback_query(filters.regex("upload"))
async def doc(bot, update):
    rkn_processing = await update.message.edit("`Processing...`")
    if not os.path.isdir("Metadata"):
        os.mkdir("Metadata")
    if not os.path.isdir("Renames"):
        os.mkdir("Renames")

    total, used, free = shutil.disk_usage("/")
    if free < 300 * 1024 * 1024:
        return await rkn_processing.edit("⚠️ Not enough disk space. Please try again later.")

    user_id = int(update.message.chat.id)
    new_filename_ = update.message.text.split(":-", 1)[-1].strip()
    user_data = await digital_botz.get_user_data(user_id)

    try:
        prefix = await digital_botz.get_prefix(user_id)
        suffix = await digital_botz.get_suffix(user_id)
        new_filename = add_prefix_suffix(new_filename_, prefix, suffix)
    except Exception as e:
        return await rkn_processing.edit(f"❌ Prefix/Suffix error: {e}")

    file = update.message.reply_to_message
    media = getattr(file, file.media.value)
    file_path = f"Renames/{new_filename}"
    metadata_path = f"Metadata/{new_filename}"

    await rkn_processing.edit("`Downloading...`")
    if bot.premium and bot.uploadlimit:
        limit = user_data.get('uploadlimit', DEFAULT_LIMIT)
        used = user_data.get('used_limit', 0)
        await digital_botz.set_used_limit(user_id, int(used) + int(media.file_size))

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

    dl_path = await download_file()
    final_path = await prepare_metadata()
    await rkn_processing.edit("`Uploading...`")

    duration = 0
    try:
        parser = createParser(final_path)
        metadata = extractMetadata(parser) if parser else None
        if metadata and metadata.has("duration"):
            duration = metadata.get("duration").seconds
    except: pass

    c_caption = await digital_botz.get_caption(user_id)
    c_thumb = await digital_botz.get_thumbnail(user_id)
    caption = c_caption.format(filename=new_filename, filesize=humanbytes(media.file_size), duration=convert(duration)) if c_caption else f"**{new_filename}**"

    ph_path = None
    try:
        if c_thumb:
            ph_path = await bot.download_media(c_thumb)
        elif media.thumbs:
            ph_path = await bot.download_media(media.thumbs[0].file_id)
        if ph_path:
            Image.open(ph_path).convert("RGB").resize((320, 320)).save(ph_path, "JPEG")
    except: ph_path = None

    type = update.data.split("_")[1]
    try:
        send_method = {
            "document": bot.send_document,
            "video": bot.send_video,
            "audio": bot.send_audio
        }[type]
        send_args = dict(
            chat_id=update.message.chat.id,
            caption=caption,
            progress=progress_for_pyrogram,
            progress_args=(UPLOAD_TEXT, rkn_processing, time.time())
        )
        if ph_path: send_args['thumb'] = ph_path
        if type == "video" or type == "audio":
            send_args['duration'] = duration
        send_args[type] = final_path
        await send_method(**send_args)
    except Exception as e:
        await rkn_processing.edit(f"Upload failed: {e}")

    await remove_path(ph_path, file_path, dl_path, metadata_path)
    if os.path.exists("Renames"): shutil.rmtree("Renames", ignore_errors=True)
    if os.path.exists("Metadata"): shutil.rmtree("Metadata", ignore_errors=True)
    await rkn_processing.edit("✅ Uploaded Successfully.")
