from datetime import datetime
from typing import Dict, List, Optional

from bson import ObjectId

from skillarena_chat.db.database import db
from skillarena_chat.models import ChatMessage, Message


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
