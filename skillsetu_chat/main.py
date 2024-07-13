import os
from fastapi import (
    FastAPI,
    WebSocket,
    WebSocketDisconnect,
    Request,
    Depends,
    HTTPException,
)
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
import logging
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime
from fastapi.middleware.cors import CORSMiddleware
from .utils.manager import ConnectionManager
import json
from .utils.services import (
    get_current_user,
    get_chat_collection_name,
    create_access_token,
)

current_dir = os.path.dirname(os.path.abspath(__file__))

app = FastAPI()
templates = Jinja2Templates(directory=os.path.join(current_dir, "templates"))
logger = logging.getLogger(__name__)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# MongoDB connection
MONGO_URL = "mongodb://localhost:27017"
client = AsyncIOMotorClient(MONGO_URL)
db = client.chatapp

manager = ConnectionManager()


@app.get("/", response_class=HTMLResponse)
async def get(request: Request):
    return templates.TemplateResponse("chat.html", {"request": request})


@app.websocket("/ws/{token}")
async def websocket_endpoint(websocket: WebSocket, token: str):
    try:
        user_id = await get_current_user(token)
    except HTTPException:
        await websocket.close(code=1008)  # Policy Violation
        return

    await manager.connect(websocket, user_id)
    logger.info(f"User {user_id} connected")

    try:
        while True:
            data = await websocket.receive_json()
            receiver_id = data.get("receiver")
            message = data.get("message")

            if not receiver_id or not message:
                continue

            chat_collection_name = get_chat_collection_name(user_id, receiver_id)
            chat_collection = db[chat_collection_name]

            # Store the message in MongoDB
            new_message = await chat_collection.insert_one(
                {
                    "sender": user_id,
                    "receiver": receiver_id,
                    "message": message,
                    "timestamp": datetime.utcnow(),
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
            await manager.send_personal_message(
                json.dumps(message_to_send), receiver_id
            )

    except WebSocketDisconnect:
        manager.disconnect(user_id)
        logger.info(f"User {user_id} disconnected")


@app.get("/chat_history/{other_user_id}")
async def get_chat_history(
    other_user_id: str, current_user: str = Depends(get_current_user)
):
    chat_collection_name = get_chat_collection_name(current_user, other_user_id)
    chat_collection = db[chat_collection_name]

    cursor = chat_collection.find(
        {
            "$or": [
                {"sender": current_user, "receiver": other_user_id},
                {"sender": other_user_id, "receiver": current_user},
            ]
        }
    ).sort("timestamp", 1)

    chat_history = await cursor.to_list(length=None)
    return [
        {
            "sender": chat["sender"],
            "receiver": chat["receiver"],
            "message": chat["message"],
            "timestamp": chat["timestamp"].isoformat(),
        }
        for chat in chat_history
    ]


# For demonstration purposes, we'll create a simple endpoint to generate tokens
@app.get("/get_token/{user_id}")
async def get_token(user_id: str):
    access_token = create_access_token(data={"sub": user_id})
    return {"access_token": access_token, "token_type": "bearer"}
