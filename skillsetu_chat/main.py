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
from bson import ObjectId
from datetime import datetime, timedelta
from fastapi.middleware.cors import CORSMiddleware
from jose import JWTError, jwt
from fastapi.security import OAuth2PasswordBearer
from .utils.manager import ConnectionManager

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

# JWT settings
SECRET_KEY = "your-secret-key"  # Change this to a secure random key
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

manager = ConnectionManager()


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
            await chat_collection.insert_one(
                {
                    "sender": user_id,
                    "receiver": receiver_id,
                    "message": message,
                    "timestamp": datetime.utcnow(),
                }
            )

            # Send the message to the receiver if they're connected
            await manager.send_personal_message(f"{user_id}: {message}", receiver_id)

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
