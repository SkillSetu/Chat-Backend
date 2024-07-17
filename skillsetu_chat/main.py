import os
from fastapi import (
    FastAPI,
    WebSocket,
    WebSocketDisconnect,
    Request,
    Depends,
    HTTPException,
    status,
)
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
import logging
from fastapi.middleware.cors import CORSMiddleware
from .utils.manager import manager
from .utils.services import (
    get_current_user,
    get_chat_collection_name,
    create_access_token,
    handle_send_chat_message,
    compress_file,
)
from .utils.database import db
from .utils.models import ChatMessage
import boto3
from botocore.exceptions import ClientError
from fastapi import File, UploadFile, Form
from typing import List
from dotenv import load_dotenv
from .utils.notifications import send_push_message

load_dotenv()

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

MAX_FILE_SIZE = 10 * 1024 * 1024
s3_client = boto3.client(
    "s3",
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    region_name=os.getenv("AWS_REGION"),
)


@app.get("/", response_class=HTMLResponse)
async def get(request: Request):
    try:
        return templates.TemplateResponse("chat.html", {"request": request})
    except Exception as e:
        logger.error(f"Error rendering chat template: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@app.websocket("/ws/{token}")
async def websocket_endpoint(websocket: WebSocket, token: str):
    try:
        user_id = await get_current_user(token)
    except HTTPException as e:
        logger.warning(f"Invalid token: {str(e)}")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await manager.connect(websocket, user_id)
    logger.info(f"User {user_id} connected")

    try:
        while True:
            data = await websocket.receive_json()
            try:
                chat_message = ChatMessage(**data)
            except ValueError as e:
                logger.error(f"Invalid message format: {str(e)}")
                await websocket.send_json({"error": "Invalid message format"})
                continue

            chat_message.sender = user_id

            if not chat_message.receiver or not chat_message.message:
                await websocket.send_json({"error": "Missing receiver or message"})
                continue

            try:
                await handle_send_chat_message(chat_message)
                if not await manager.is_connected(chat_message.receiver):
                    await send_push_message(
                        chat_message.receiver,
                        f"New message from {user_id}",
                        {"message": chat_message.message},
                    )

            except Exception as e:
                logger.error(f"Error handling chat message: {str(e)}")
                await websocket.send_json({"error": "Failed to send message"})

    except WebSocketDisconnect:
        manager.disconnect(user_id)
        logger.info(f"User {user_id} disconnected")

    except Exception as e:
        logger.error(f"Unexpected error in WebSocket connection: {str(e)}")
        await websocket.close(code=status.WS_1011_INTERNAL_ERROR)


@app.get("/chat_history/{other_user_id}")
async def get_chat_history(
    other_user_id: str, current_user: str = Depends(get_current_user)
):
    try:
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
    except Exception as e:
        logger.error(f"Error retrieving chat history: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve chat history",
        )


@app.get("/get_token/{user_id}")
async def get_token(user_id: str):
    try:
        access_token = create_access_token(data={"sub": user_id})
        return {"access_token": access_token, "token_type": "bearer"}
    except Exception as e:
        logger.error(f"Error creating access token: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create access token",
        )


@app.post("/upload_files")
async def upload_files(
    files: List[UploadFile] = File(...),
    current_user_id: str = Depends(get_current_user),
    other_user_id: str = Form(...),
):
    try:
        uploaded_files = []
        for file in files:
            # Check file size
            file.file.seek(0, 2)
            file_size = file.file.tell()
            file.file.seek(0)

            if file_size > MAX_FILE_SIZE:
                raise HTTPException(
                    status_code=400,
                    detail=f"File {file.filename} exceeds the maximum size limit of {MAX_FILE_SIZE / (1024 * 1024)} MB",
                )

            # Compress the file
            compressed_file = compress_file(file)
            chatid = get_chat_collection_name(current_user_id, other_user_id)
            file_name = f"{chatid}/{file.filename}"
            content_type = (
                "application/gzip"
                if not file.content_type.startswith("image")
                else file.content_type
            )

            s3_client.upload_fileobj(
                compressed_file,
                os.getenv("S3_BUCKET_NAME"),
                file_name,
                ExtraArgs={"ContentType": content_type},
            )

            # Generate the URL for the uploaded file
            url = f"https://{os.getenv('S3_BUCKET_NAME')}.s3.amazonaws.com/{file_name}"

            uploaded_files.append(
                {
                    "original_file_name": file.filename,
                    "stored_file_name": file_name,
                    "url": url,
                }
            )

        return {
            "message": f"{len(uploaded_files)} file(s) uploaded successfully",
            "files": uploaded_files,
        }

    except ClientError as e:
        logger.error(f"Error uploading file(s) to S3: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to upload file(s)")

    except HTTPException as he:
        raise he

    except Exception as e:
        logger.error(f"Unexpected error during file upload: {str(e)}")
        raise HTTPException(status_code=500, detail="An unexpected error occurred")


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"message": exc.detail},
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {str(exc)}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"message": "An unexpected error occurred"},
    )
