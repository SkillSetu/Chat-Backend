import gzip
import io
import logging
import os
from datetime import datetime, timedelta
from typing import Dict, Optional

from PIL import Image
from dotenv import load_dotenv
from fastapi import Depends, HTTPException, UploadFile, status
from fastapi.security import OAuth2PasswordBearer
from jose import ExpiredSignatureError, JWTError, jwt

from .database import db
from .manager import manager
from .models import ChatMessage, FileData, Message


load_dotenv(override=True)


# Constants
ACCESS_TOKEN_SECRET = os.getenv("ACCESS_TOKEN_SECRET")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# Setup
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
logger = logging.getLogger(__name__)


class TokenCreationError(Exception):
    """Custom exception for token creation errors."""


class DatabaseOperationError(Exception):
    """Custom exception for database operation errors."""


def create_access_token(data: Dict[str, str]) -> str:
    """
    Create a new access token.

    Args:
        data: A dictionary containing the data to encode in the token.

    Returns:
        str: The encoded JWT token.

    Raises:
        TokenCreationError: If token creation fails.
    """

    try:
        to_encode = data.copy()
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        to_encode.update({"exp": expire})
        return jwt.encode(to_encode, ACCESS_TOKEN_SECRET, algorithm=ALGORITHM)
    except Exception as e:
        logger.error(f"Error creating access token: {str(e)}")
        raise TokenCreationError("Failed to create access token") from e


async def get_current_user(token: str = Depends(oauth2_scheme)) -> str:
    """
    Validate the access token and return the current user.

    Args:
        token: The JWT token to validate.

    Returns:
        str: The user ID extracted from the token.

    Raises:
        HTTPException: If the token is invalid or expired.
    """

    try:
        payload = jwt.decode(token, ACCESS_TOKEN_SECRET, algorithms=[ALGORITHM])
        user_id: str | None = payload.get("sub")

        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return user_id

    except ExpiredSignatureError:
        logger.warning("Token has expired")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )

    except JWTError as e:
        logger.error(f"JWT error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e


async def get_chat(user_id1: str, user_id2: str) -> Optional[Dict]:
    """
    Retrieve a chat between two users.

    Args:
        user_id1: The ID of the first user.
        user_id2: The ID of the second user.

    Returns:
        Optional[Dict]: The chat document if found, None otherwise.
    """

    users = sorted([user_id1, user_id2])
    return await db.get_collection("messages").find_one({"users": users})


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
            user_id=chat_message.sender,
            message_id=chat_message.id,
            updated_status="delivered",
        )
        await manager.send_receipt_update(
            user_id=chat_message.receiver,
            message_id=chat_message.id,
            updated_status="delivered",
        )

    except Exception as e:
        logger.error(f"Error handling chat message: {str(e)}")
        raise DatabaseOperationError("Failed to handle chat message") from e


def create_chat_message(data: Dict) -> Message:
    """
    Create a Message object from dictionary data.

    Args:
        data: A dictionary containing message data.

    Returns:
        Message: The created Message object.

    Raises:
        ValueError: If the message data is invalid.
    """

    try:
        if "file" in data and data["file"]:
            data["file"] = FileData(**data["file"])
        return Message(**data)
    except Exception as e:
        logger.error(f"Error creating chat message: {str(e)}")
        raise ValueError("Invalid chat message data") from e


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


async def get_all_user_chats(user_id: str) -> list[Message]:
    """Get all chats for a user.

    Args:
        user_id (str): The user ID.

    Returns:
        list[Message]: A list of chat messages.
    """

    chats = (
        await db.get_collection("messages")
        .find({"users": user_id})
        .to_list(length=1000)
    )

    # convert all ObjectIds to strings for JSON serialization
    for chat in chats:
        chat["_id"] = str(chat["_id"])

    return chats


async def mark_messages_as_read(chat: ChatMessage, current_user_id: str):
    """Mark messages as read when a user reads a chat.

    Args:
        chat (ChatMessage): The chat to mark messages in.
        current_user_id (str): The ID of the current user.

    Raises:
        DatabaseOperationError: If database operations fail.
    """

    messages = db.get_collection("messages")
    all_messages = chat["messages"]
    delivered_messages = [
        message for message in all_messages if message["status"] == "delivered"
    ]
    to_update_delivered_messages = [
        message
        for message in delivered_messages
        if message["receiver"] == current_user_id
    ]

    try:
        for message in to_update_delivered_messages:
            await messages.update_one(
                {"_id": chat["_id"], "messages.id": message["id"]},
                {"$set": {"messages.$.status": "read"}},
            )

    except Exception as e:
        logger.error(f"Error marking messages as read: {str(e)}")
        raise DatabaseOperationError("Failed to mark messages as read") from e


async def create_empty_chat(user_id: str, other_user_id: str) -> ChatMessage:
    """Create an empty chat for a user.

    Args:
        user_id (str): The user ID.

    Returns:
        ChatMessage: The created chat message.
    """

    chat = ChatMessage(
        messages=[],
        users=sorted([user_id, other_user_id]),
        created_at=datetime.utcnow(),
        last_updated=datetime.utcnow(),
    )
    await db.get_collection("messages").insert_one(chat.dict())
    return chat
