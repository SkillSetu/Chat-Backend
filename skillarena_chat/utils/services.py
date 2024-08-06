import gzip
import io
import logging
from datetime import datetime

from PIL import Image
from fastapi import UploadFile
from fastapi.security import OAuth2PasswordBearer

from ..db.database import db
from ..models import ChatMessage, Message
from ..services.chat import get_chat
from ..services.exceptions import DatabaseOperationError
from .manager import manager


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
logger = logging.getLogger(__name__)


async def handle_send_chat_message(chat_message: Message) -> None:
    """
    Handle sending a chat message, including database updates and WebSocket notifications.

    Args:
        chat_message: The message to be sent.

    Raises:
        DatabaseOperationError: If database operations fail.
    """

    messages = db.get_collection("messages")
    chat_doc = await get_chat(chat_message.sender, chat_message.receiver)

    try:
        if chat_doc:
            await messages.update_one(
                {"_id": chat_doc["_id"]},
                {
                    "$push": {"messages": chat_message.dict()},
                    "$set": {"last_updated": datetime.utcnow()},
                },
            )
        else:
            new_chat = ChatMessage(
                messages=[chat_message],
                users=sorted([chat_message.sender, chat_message.receiver]),
                created_at=datetime.utcnow(),
                last_updated=datetime.utcnow(),
            )
            await messages.insert_one(new_chat.dict())
            chat_doc = await get_chat(chat_message.sender, chat_message.receiver)

        message_json = chat_message.model_dump_json()
        await manager.send_personal_message(message_json, chat_message.sender)
        await manager.send_personal_message(message_json, chat_message.receiver)

        await messages.update_one(
            {"_id": chat_doc["_id"], "messages.id": chat_message.id},
            {"$set": {"messages.$.status": "delivered"}},
        )

        await manager.send_receipt_update(
            chat_id=str(chat_doc["_id"]),
            user_id=chat_message.sender,
            message_id=chat_message.id,
            updated_status="delivered",
        )
        await manager.send_receipt_update(
            chat_id=str(chat_doc["_id"]),
            user_id=chat_message.receiver,
            message_id=chat_message.id,
            updated_status="read",
        )

    except Exception as e:
        logger.error(f"Error handling chat message: {str(e)}")
        raise DatabaseOperationError("Failed to handle chat message") from e


def compress_file(file: UploadFile) -> io.BytesIO:
    """
    Compress the given file.

    Args:
        file: The UploadFile object to compress.

    Returns:
        io.BytesIO: A BytesIO object containing the compressed file data.
    """

    compressed_file = io.BytesIO()

    if file.content_type.startswith("image"):
        with Image.open(file.file) as img:
            img.save(compressed_file, format=img.format, optimize=True, quality=85)
    else:
        with gzip.GzipFile(fileobj=compressed_file, mode="wb") as gz:
            gz.write(file.file.read())

    compressed_file.seek(0)
    return compressed_file
