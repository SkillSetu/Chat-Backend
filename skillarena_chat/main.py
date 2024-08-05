import logging
import os
from typing import List

from fastapi import (
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

from .models import Message
from .services.auth import create_access_token, get_current_user
from .utils.manager import manager
from .utils.middlewares import AuthMiddleware
from .utils.s3 import process_and_upload_file
from .utils.services import (
    block_user,
    create_empty_chat,
    get_all_user_chats,
    get_chat,
    handle_send_chat_message,
    mark_messages_as_read,
)


logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

current_dir = os.path.dirname(os.path.abspath(__file__))

app = FastAPI()
templates = Jinja2Templates(directory=os.path.join(current_dir, "templates"))

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

exempt_routes = ["/", "/get_token/{user_id}"]
app.add_middleware(AuthMiddleware, exempt_routes=exempt_routes)


@app.get("/", response_class=HTMLResponse)
async def get(request: Request):
    try:
        return templates.TemplateResponse("chat.html", {"request": request})

    except Exception:
        logger.exception("Error rendering chat template")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@app.websocket("/ws/{token}")
async def websocket_endpoint(websocket: WebSocket, token: str):
    user_id = None
    try:
        user_id = await get_current_user(token)
        await manager.connect(websocket, user_id)
        logger.info(f"User {user_id} connected")

        while True:
            data = await websocket.receive_json()
            await process_websocket_message(websocket, data, user_id)

    except HTTPException as e:
        logger.warning(f"Invalid token for user {user_id}: {e.detail}")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)

    except WebSocketDisconnect:
        if user_id:
            manager.disconnect(user_id)
            logger.info(f"User {user_id} disconnected")
    except Exception:
        logger.exception(f"Unexpected error in WebSocket connection for user {user_id}")
        await websocket.close(code=status.WS_1011_INTERNAL_ERROR)


async def process_websocket_message(websocket: WebSocket, data: dict, user_id: str):
    try:
        data["sender"] = user_id
        chat_message = Message(**data)

        if not chat_message.receiver or not chat_message.message:
            raise ValueError("Missing receiver or message")

        await handle_send_chat_message(chat_message)
        logger.info(f"Message sent from {user_id} to {chat_message.receiver}")

        # TODO: Uncomment this when push notifications are implemented
        # if not await manager.is_connected(chat_message.receiver):
        #     await send_push_message(
        #         chat_message.receiver,
        #         f"New message from {user_id}",
        #         {"message": chat_message.message},
        #     )

    except ValueError as e:
        logger.error(f"Invalid message format from user {user_id}: {str(e)}")
        await websocket.send_json({"error": str(e)})

    except Exception:
        logger.exception(f"Error handling chat message from user {user_id}")
        await websocket.send_json({"error": "Failed to send message"})


@app.get("/chat_history/{other_user_id}")
async def get_chat_history(request: Request, other_user_id: str):
    try:
        current_user = request.state.user_id
        chat = await get_chat(current_user, other_user_id)

        if not chat:
            chat = await create_empty_chat(current_user, other_user_id)
            logger.info(f"Created empty chat for {current_user} and {other_user_id}")
        else:
            await mark_messages_as_read(chat, current_user)
            logger.info(
                f"Marked messages as read for {current_user} in chat with {other_user_id}"
            )

        updated_chat = await get_chat(current_user, other_user_id)
        return updated_chat["messages"] if updated_chat else []

    except Exception:
        logger.exception(
            f"Error retrieving chat history for {current_user} and {other_user_id}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve chat history",
        )


@app.get("/chat_history")
async def get_user_chat_history(request: Request):
    try:
        user_id = request.state.user_id
        chats = await get_all_user_chats(user_id)
        logger.info(f"Retrieved {len(chats)} chats for user {user_id}")
        return chats

    except Exception:
        logger.exception(f"Error retrieving chat history for user {user_id}")
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve chat history",
        )


@app.get("/get_token/{user_id}")
async def get_token(user_id: str):
    try:
        access_token = create_access_token(data={"sub": user_id})
        logger.info(f"Created access token for user {user_id}")
        return {"access_token": access_token, "token_type": "bearer"}

    except Exception:
        logger.exception(f"Error creating access token for user {user_id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create access token",
        )


# TODO: Uncomment this when push notifications are implemented
# @app.post("/send_push_message")
# async def send_push_message_endpoint(
#     client_id: str = Form(...),
#     message: str = Form(...),
#     extra: dict = Form(None),
# ):
#     try:
#         response = await send_push_message(client_id, message, extra)
#         logger.info(f"Push message sent to client {client_id}")
#         return response

#     except HTTPException as e:
#         logger.error(f"Error sending push message to client {client_id}: {e.detail}")
#         raise e

#     except Exception:
#         logger.exception(f"Unexpected error sending push message to client {client_id}")
#         raise HTTPException(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             detail="Failed to send push message",
#         )


@app.post("/upload_files")
async def upload_files(
    request: Request,
    files: List[UploadFile] = File(...),
    other_user_id: str = Form(...),
):
    try:
        current_user_id = request.state.user_id
        chat = await get_chat(current_user_id, other_user_id)
        if not chat or "_id" not in chat:
            raise ValueError("Chat not found")

        chatid = chat["_id"]
        uploaded_files = [process_and_upload_file(file, chatid) for file in files]
        logger.info(f"Uploaded {len(uploaded_files)} file(s) for chat {chatid}")

        return {
            "message": f"{len(uploaded_files)} file(s) uploaded successfully",
            "files": uploaded_files,
        }

    except ValueError as ve:
        logger.error(f"Validation error during file upload: {str(ve)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))

    except Exception:
        logger.exception(
            f"Unexpected error during file upload for users {current_user_id} and {other_user_id}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during file upload",
        )


@app.post("/block_user/{user_id}")
async def block_user_endpoint(request: Request, user_id: str):
    try:
        current_user_id = request.state.user_id

        await block_user(current_user_id, user_id)

        logger.info(f"Blocked user {user_id} for user {current_user_id}")
        return {"message": f"User {user_id} blocked successfully"}

    except Exception:
        logger.exception(f"Error blocking user {user_id} for user {current_user_id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to block user",
        )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    logger.error(f"HTTP exception: {exc.status_code} - {exc.detail}")

    if exc.status_code == 404:
        return JSONResponse(
            status_code=404,
            content={"detail": "The requested resource was not found"},
        )

    return JSONResponse(status_code=exc.status_code, content={"message": exc.detail})


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"message": "An unexpected error occurred"},
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
