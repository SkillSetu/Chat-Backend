from jose import JWTError, jwt
from fastapi import Depends, HTTPException
from datetime import datetime, timedelta
from fastapi.security import OAuth2PasswordBearer
from .manager import manager
import json
from .database import db
from typing import Optional
from .models import ChatMessage, FileData

SECRET_KEY = "your-secret-key"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=401,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
    except JWTError:
        raise credentials_exception
    return user_id


def get_chat_collection_name(user1_id: str, user2_id: str) -> str:
    if user1_id is None or user2_id is None:
        raise ValueError("Both user IDs must be provided")

    # Use the entire user ID, but ensure it's a string and remove any non-alphanumeric characters
    clean_id1 = "".join(filter(str.isalnum, str(user1_id)))
    clean_id2 = "".join(filter(str.isalnum, str(user2_id)))

    # Sort the cleaned IDs
    sorted_ids = sorted([clean_id1, clean_id2])

    # Create a unique, consistent name for the chat collection
    return f"chat_{sorted_ids[0]}_{sorted_ids[1]}"


async def handle_send_chat_message(chat_message: ChatMessage):
    chat_collection_name = get_chat_collection_name(
        chat_message.sender, chat_message.receiver
    )
    chat_collection = db[chat_collection_name]

    chat_dict = chat_message.dict(exclude={"id"})
    new_message = await chat_collection.insert_one(chat_dict)

    chat_message.id = str(new_message.inserted_id)

    # Send the message to both the sender and the receiver
    message_json = chat_message.json()
    await manager.send_personal_message(message_json, chat_message.sender)
    await manager.send_personal_message(message_json, chat_message.receiver)


# You might want to add this function to create a ChatMessage object
def create_chat_message(data: dict) -> ChatMessage:
    if "file" in data and data["file"]:
        data["file"] = FileData(**data["file"])
    return ChatMessage(**data)
