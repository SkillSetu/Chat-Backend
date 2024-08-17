import logging

from fastapi import WebSocket

from skillarena_chat.db.database import db
from skillarena_chat.models import ChatMessage, Message
from skillarena_chat.services.chat import get_chat, get_recipients_list


logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections."""

    def __init__(self):
        self.active_connections: dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, user_id: str):
        await websocket.accept()

        self.active_connections[user_id] = websocket

        recipients_list = await get_recipients_list(user_id)
        for recipient in recipients_list:
            await websocket.send_json(
                {
                    "type": "recipient_list",
                    "data": {
                        "chat_id": recipient["_id"],
                        "receiver": recipient["receiver"],
                        "name": recipient["name"],
                        "avatar": recipient["avatar"],
                        "last_message": recipient["last_message"],
                        "is_blocked": recipient["is_blocked"],
                        "last_updated": recipient["last_updated"].isoformat(),
                    },
                }
            )

    def disconnect(self, user_id: str):
        if user_id in self.active_connections:
            del self.active_connections[user_id]

        del self.active_connections[user_id]

    async def is_connected(self, user_id: str):
        return user_id in self.active_connections


class ChatManager:
    def __init__(self):
        self.active_chats: dict[str, WebSocket] = {}

    async def connect(
        self, websocket: WebSocket, user_id: str, other_user_id: str
    ) -> None:
        await websocket.accept()
        logger.info(f"Chat between {user_id} and {other_user_id} established")

        self.active_chats[user_id] = websocket
        chat = await get_chat(user_id, other_user_id)

        if chat is None:
            chat_collection = db.get_collection("chats")
            newChat = ChatMessage(users=sorted([user_id, other_user_id]), messages=[])

            await chat_collection.insert_one(newChat.dict())

            return

        for message in chat["messages"]:
            await websocket.send_json(
                {
                    "type": "message",
                    "data": message,
                }
            )

    async def send_message(self, message: Message, user_id: str) -> None:
        if user_id in self.active_chats:
            await self.active_chats[user_id].send_json(
                {"type": "message", "data": message.dict()}
            )


connection_manager = ConnectionManager()
chat_manager = ChatManager()
