import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
import logging
from fastapi_limiter.depends import WebSocketRateLimiter
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
from datetime import datetime
from fastapi.middleware.cors import CORSMiddleware

current_dir = os.path.dirname(os.path.abspath(__file__))

app = FastAPI()
templates = Jinja2Templates(directory=os.path.join(current_dir, "templates"))
logger = logging.getLogger(__name__)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# MongoDB connection
MONGO_URL = "mongodb://localhost:27017"  # Replace with your MongoDB URL if different
client = AsyncIOMotorClient(MONGO_URL)
db = client.chatapp  # Replace 'chatapp' with your preferred database name
messages_collection = db.messages


class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[str, list[WebSocket]] = {
            "chat1": [],
            "chat2": [],
            "chat3": [],
        }

    async def connect(self, websocket: WebSocket, chat_id: str):
        await websocket.accept()
        if chat_id not in self.active_connections:
            self.active_connections[chat_id] = []
        self.active_connections[chat_id].append(websocket)

    def disconnect(self, websocket: WebSocket, chat_id: str):
        self.active_connections[chat_id].remove(websocket)

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast(self, message: str, chat_id: str):
        for connection in self.active_connections[chat_id]:
            await connection.send_text(message)


manager = ConnectionManager()


@app.get("/", response_class=HTMLResponse)
async def get(request: Request):
    return templates.TemplateResponse("chat.html", {"request": request})


@app.websocket("/ws/{chat_id}/{client_id}")
async def websocket_endpoint(websocket: WebSocket, chat_id: str, client_id: int):
    await manager.connect(websocket, chat_id)
    logger.info(f"Client #{client_id} joined the chat {chat_id}")
    ratelimit = WebSocketRateLimiter(
        times=50, seconds=10, callback=lambda: manager.disconnect(websocket, chat_id)
    )

    try:
        while True:
            data = await websocket.receive_text()

            # Store message in MongoDB
            message = {
                "chat_id": chat_id,
                "client_id": client_id,
                "message": data,
                "timestamp": datetime.utcnow(),
            }
            await messages_collection.insert_one(message)

            await manager.send_personal_message(f"You wrote: {data}", websocket)
            await manager.broadcast(f"Client #{client_id} says: {data}", chat_id)
    except WebSocketDisconnect:
        manager.disconnect(websocket, chat_id)
        logger.info(f"Client #{client_id} left the chat {chat_id}")
        await manager.broadcast(f"Client #{client_id} left the chat", chat_id)


# New route to fetch chat history
@app.get("/chat_history/{chat_id}")
async def get_chat_history(chat_id: str):
    cursor = messages_collection.find({"chat_id": chat_id}).sort("timestamp", 1)
    messages = await cursor.to_list(length=None)
    return [
        {
            "id": str(msg["_id"]),
            "client_id": msg["client_id"],
            "message": msg["message"],
            "timestamp": msg["timestamp"].isoformat(),
        }
        for msg in messages
    ]
