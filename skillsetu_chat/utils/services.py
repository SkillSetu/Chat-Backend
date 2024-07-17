import logging
from jose import JWTError, jwt, ExpiredSignatureError
from fastapi import Depends, HTTPException, status, UploadFile
from datetime import datetime, timedelta
from fastapi.security import OAuth2PasswordBearer
from .manager import manager
from .database import db
from .models import ChatMessage, FileData
import io
import gzip
from PIL import Image

SECRET_KEY = "your-secret-key"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
logger = logging.getLogger(__name__)


class TokenCreationError(Exception):
    pass


class DatabaseOperationError(Exception):
    pass


def create_access_token(data: dict):
    try:
        to_encode = data.copy()
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
        return encoded_jwt
    except Exception as e:
        logger.error(f"Error creating access token: {str(e)}")
        raise TokenCreationError("Failed to create access token")


async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except ExpiredSignatureError:
        logger.warning("Token has expired")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except JWTError as e:
        logger.error(f"JWT error: {str(e)}")
        raise credentials_exception
    return user_id


def get_chat_collection_name(user1_id: str, user2_id: str) -> str:
    try:
        clean_id1 = "".join(filter(str.isalnum, str(user1_id)))
        clean_id2 = "".join(filter(str.isalnum, str(user2_id)))

        sorted_ids = sorted([clean_id1, clean_id2])

        return f"chat_{sorted_ids[0]}_{sorted_ids[1]}"
    except Exception as e:
        logger.error(f"Error generating chat collection name: {str(e)}")
        raise ValueError("Invalid user IDs")


async def handle_send_chat_message(chat_message: ChatMessage):
    try:
        chat_collection_name = get_chat_collection_name(
            chat_message.sender, chat_message.receiver
        )
        chat_collection = db[chat_collection_name]

        chat_dict = chat_message.dict(exclude={"id"})
        new_message = await chat_collection.insert_one(chat_dict)

        chat_message.id = str(new_message.inserted_id)

        message_json = chat_message.model_dump_json()
        await manager.send_personal_message(message_json, chat_message.sender)
        await manager.send_personal_message(message_json, chat_message.receiver)
    except Exception as e:
        logger.error(f"Error handling chat message: {str(e)}")
        raise DatabaseOperationError("Failed to send chat message")


def create_chat_message(data: dict) -> ChatMessage:
    try:
        if "file" in data and data["file"]:
            data["file"] = FileData(**data["file"])
        return ChatMessage(**data)
    except Exception as e:
        logger.error(f"Error creating chat message: {str(e)}")
        raise ValueError("Invalid chat message data")


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
