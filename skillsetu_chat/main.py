import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
import logging
from fastapi_limiter.depends import WebSocketRateLimiter

current_dir = os.path.dirname(os.path.abspath(__file__))

app = FastAPI()
templates = Jinja2Templates(directory=os.path.join(current_dir, "templates"))
logger = logging.getLogger(__name__)


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
            await manager.send_personal_message(f"You wrote: {data}", websocket)
            await manager.broadcast(f"Client #{client_id} says: {data}", chat_id)
    except WebSocketDisconnect:
        manager.disconnect(websocket, chat_id)
        logger.info(f"Client #{client_id} left the chat {chat_id}")
        await manager.broadcast(f"Client #{client_id} left the chat", chat_id)
