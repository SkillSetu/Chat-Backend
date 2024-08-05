from datetime import datetime
from typing import Dict, List, Optional

from ..db.database import db
from ..models import ChatMessage, Message
from .exceptions import DatabaseOperationError


async def get_chat(user_id1: str, user_id2: str) -> Optional[Dict]:
    users = sorted([user_id1, user_id2])
    return await db.get_collection("messages").find_one({"users": users})


async def get_all_user_chats(user_id: str) -> List[Message]:
    chats = (
        await db.get_collection("messages")
        .find({"users": user_id})
        .to_list(length=1000)
    )

    for chat in chats:
        chat["_id"] = str(chat["_id"])

    return chats


async def mark_messages_as_read(chat: ChatMessage, current_user_id: str):
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
        raise DatabaseOperationError("Failed to mark messages as read") from e


async def create_empty_chat(user_id: str, other_user_id: str) -> ChatMessage:
    chat = ChatMessage(
        messages=[],
        users=sorted([user_id, other_user_id]),
        created_at=datetime.utcnow(),
        last_updated=datetime.utcnow(),
    )

    await db.get_collection("messages").insert_one(chat.dict())
    return chat


async def block_user(user_id: str, blocked_user_id: str):
    try:
        chat = await get_chat(user_id, blocked_user_id)
        if not chat:
            raise ValueError("Chat not found")

        await db.get_collection("messages").update_one(
            {"_id": chat["_id"]},
            {"$set": {"is_blocked": True, "blocked_by": user_id}},
        )

    except Exception as e:
        raise DatabaseOperationError("Failed to block user") from e
