import gzip
import io
import logging

from PIL import Image
from fastapi import UploadFile
from fastapi.security import OAuth2PasswordBearer

from skillarena_chat.db.database import db
from skillarena_chat.models import Message
from skillarena_chat.services.chat import get_chat
from skillarena_chat.utils.manager import chat_manager


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
logger = logging.getLogger(__name__)


async def handle_send_chat_message(message: Message):
    chats_collection = db.get_collection("chats")
    chat = await get_chat(message.sender, message.receiver)

    await chat_manager.send_message(message, message.sender)
    await chat_manager.send_message(message, message.receiver)

    await chats_collection.update_one(
        {"_id": chat["_id"]}, {"$push": {"messages": message.dict()}}
    )


def compress_file(file: UploadFile) -> io.BytesIO:
    compressed_file = io.BytesIO()

    if file.content_type.startswith("image"):
        with Image.open(file.file) as img:
            img.save(compressed_file, format=img.format, optimize=True, quality=85)
    else:
        with gzip.GzipFile(fileobj=compressed_file, mode="wb") as gz:
            gz.write(file.file.read())

    compressed_file.seek(0)
    return compressed_file
