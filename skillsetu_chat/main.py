import logging
import os
from typing import List

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from .utils.manager import manager
from .utils.models import Message
from .utils.notifications import send_push_message
from .utils.s3 import process_and_upload_file
from .utils.services import (
    create_access_token,
    get_chat,
    get_current_user,
    handle_send_chat_message,
    get_all_user_chats,
    mark_messages_as_read,
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
                data["sender"] = user_id
                chat_message = Message(**data)
            except ValueError as e:
                logger.error(f"Invalid message format: {str(e)}")
                await websocket.send_json({"error": "Invalid message format"})
                continue

            if not chat_message.receiver or not chat_message.message:
                await websocket.send_json({"error": "Missing receiver or message"})
                continue

            try:
                await handle_send_chat_message(chat_message)

                # TODO: Uncomment this when push notifications are implemented
                # if not await manager.is_connected(chat_message.receiver):
                #     await send_push_message(
                #         chat_message.receiver,
                #         f"New message from {user_id}",
                #         {"message": chat_message.message},
                #     )

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
        chat = await get_chat(current_user, other_user_id)
        await mark_messages_as_read(chat, current_user)

        updated_chat = await get_chat(current_user, other_user_id)

        return updated_chat["messages"] if chat else []

    except Exception as e:
        logger.error(f"Error retrieving chat history: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve chat history",
        )


@app.get("/chat_history")
async def get_user_chat_history(current_user: str = Depends(get_current_user)):
    try:
        return await get_all_user_chats(current_user)

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


@app.post("/send_push_message")
async def send_push_message_endpoint(
    client_id: str = Form(...),
    message: str = Form(...),
    extra: dict = Form(None),
):
    try:
        response = await send_push_message(client_id, message, extra)
        return response
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error sending push message: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send push message",
        )


@app.post("/upload_files")
async def upload_files(
    files: List[UploadFile] = File(...),
    current_user_id: str = Depends(get_current_user),
    other_user_id: str = Form(...),
):
    try:
        chat = await get_chat(current_user_id, other_user_id)
        chatid = chat["_id"]

        if not chatid:
            raise HTTPException(status_code=400, detail="Chat not found")

        uploaded_files = [process_and_upload_file(file, chatid) for file in files]

        return {
            "message": f"{len(uploaded_files)} file(s) uploaded successfully",
            "files": uploaded_files,
        }

    except ValueError as ve:
        logger.error(f"Validation error: {str(ve)}")

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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
