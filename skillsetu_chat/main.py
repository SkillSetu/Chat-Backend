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
from datetime import datetime
from fastapi.middleware.cors import CORSMiddleware
from .utils.manager import manager
from .utils.services import (
    get_current_user,
    get_chat_collection_name,
    create_access_token,
    handle_send_chat_message,
)
from .utils.database import db
from .utils.models import ChatMessage

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
            chat_message = ChatMessage(**data)
            chat_message.sender = user_id

            if chat_message.file:
                logger.info(f"Received file data: {chat_message.file}")

            if not chat_message.receiver or not chat_message.message:
                continue

            await handle_send_chat_message(chat_message)

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
    return [ChatMessage(**chat).dict() for chat in chat_history]


@app.get("/get_token/{user_id}")
async def get_token(user_id: str):
    access_token = create_access_token(data={"sub": user_id})
    return {"access_token": access_token, "token_type": "bearer"}
