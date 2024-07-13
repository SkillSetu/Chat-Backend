from jose import JWTError, jwt
from fastapi import Depends, HTTPException
from datetime import datetime, timedelta
from fastapi.security import OAuth2PasswordBearer
from .manager import manager
import json
from .database import db

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


def get_chat_collection_name(user1_id: str, user2_id: str):
    sorted_ids = sorted([user1_id[-4:], user2_id[-4:]])
    return f"chat_{sorted_ids[0]}_{sorted_ids[1]}"


async def handle_send_file(user_id, receiver_id, file):
    # for now just send file name as chat message to receiver
    chat_collection_name = get_chat_collection_name(user_id, receiver_id)
    chat_collection = db[chat_collection_name]

    # Store the message in MongoDB
    new_message = await chat_collection.insert_one(
        {
            "sender": user_id,
            "receiver": receiver_id,
            "message": file.file_name,
            "timestamp": datetime.utcnow(),
            "file": {
                "file_name": file.file_name,
                "file_type": file.file_type,
                "file_content": file.file_content,
            },
        }
    )

    # Prepare the message to be sent
    message_to_send = {
        "id": str(new_message.inserted_id),
        "sender": user_id,
        "receiver": receiver_id,
        "message": file.file_name,
        "timestamp": datetime.utcnow().isoformat(),
        "file": {
            "file_name": file.file_name,
            "file_type": file.file_type,
            "file_content": file.file_content,
        },
    }

    # Send the message to both the sender and the receiver
    await manager.send_personal_message(json.dumps(message_to_send), user_id)
    await manager.send_personal_message(json.dumps(message_to_send), receiver_id)


async def handle_send_chat_message(user_id, receiver_id, message):
    chat_collection_name = get_chat_collection_name(user_id, receiver_id)
    chat_collection = db[chat_collection_name]

    # Store the message in MongoDB
    new_message = await chat_collection.insert_one(
        {
            "sender": user_id,
            "receiver": receiver_id,
            "message": message,
            "timestamp": datetime.utcnow().isoformat(),
        }
    )

    # Prepare the message to be sent
    message_to_send = {
        "id": str(new_message.inserted_id),
        "sender": user_id,
        "receiver": receiver_id,
        "message": message,
        "timestamp": datetime.utcnow().isoformat(),
    }

    # Send the message to both the sender and the receiver
    await manager.send_personal_message(json.dumps(message_to_send), user_id)
    await manager.send_personal_message(json.dumps(message_to_send), receiver_id)
