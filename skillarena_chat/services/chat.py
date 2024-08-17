from datetime import datetime
from typing import Dict, List, Optional

from bson import ObjectId

from skillarena_chat.db.database import db
from skillarena_chat.models import ChatMessage, Message
from skillarena_chat.services.exceptions import DatabaseOperationError


async def get_chat(user_id1: str, user_id2: str) -> Optional[Dict]:
    users = sorted([user_id1, user_id2])
    return await db.get_collection("chats").find_one({"users": users})


async def get_recipients_list(user_id: str) -> List[Message]:
    chats = (
        await db.get_collection("chats")
        .find(
            {"users": user_id},
        )
        .to_list(length=1000)
    )

    if len(chats) == 0:
        chats = [await create_initial_chat(user_id)]

    for chat in chats:
        receiver_id = (
            chat["users"][1] if chat["users"][0] == user_id else chat["users"][0]
        )

        chat["_id"] = str(chat["_id"])
        chat["receiver"] = receiver_id
        chat["last_message"] = (
            len(chat["messages"]) > 0 and chat["messages"][-1].get("message") or ""
        )
        chat.pop("messages")

        if receiver_id != "skillarena":
            receiver: dict = await db.get_collection("users").find_one(
                {"_id": ObjectId(receiver_id)}, {"firstName": 1, "lastName": 1}
            )

            chat["name"] = receiver["firstName"] + " " + receiver["lastName"]
        else:
            chat["name"] = "Skillarena"

    return chats


async def mark_messages_as_read(chat: ChatMessage, current_user_id: str):
    messages = db.get_collection("chats")

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


async def create_initial_chat(user_id: str) -> ChatMessage:
    chat = ChatMessage(
        messages=[
            Message(
                message="Welcome to Skillarena! 👋",
                sender="skillarena",
                receiver=user_id,
            ),
            Message(
                message="Follow the video below to understand how chat works.",
                sender="skillarena",
                receiver=user_id,
            ),
        ],
        name="Skillarena",
        users=sorted([user_id, "skillarena"]),
        created_at=datetime.utcnow(),
        last_updated=datetime.utcnow(),
    )

    await db.get_collection("chats").insert_one(chat.dict())

    chat = await get_chat(user_id, "skillarena")
    return chat


async def block_user(user_id: str, blocked_user_id: str):
    try:
        chat = await get_chat(user_id, blocked_user_id)
        if not chat:
            raise ValueError("Chat not found")

        await db.get_collection("chats").update_one(
            {"_id": chat["_id"]},
            {"$set": {"is_blocked": True, "blocked_by": user_id}},
        )

    except Exception as e:
        raise DatabaseOperationError("Failed to block user") from e


async def mark_message_as_read(chat_id: str, message_id: str):
    chats = db.get_collection("chats")

    try:
        await chats.update_one(
            {"_id": ObjectId(chat_id), "messages.id": message_id},
            {"$set": {"messages.$.status": "read"}},
        )

    except Exception as e:
        raise DatabaseOperationError("Failed to mark message as read") from e
