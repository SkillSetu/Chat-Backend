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
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from skillarena_chat.models import Message
from skillarena_chat.utils.manager import chat_manager, connection_manager
from skillarena_chat.utils.s3 import (
    generate_presigned_urls,
    process_and_upload_file,
)
from skillarena_chat.utils.services import handle_send_chat_message

from .services.chat import block_user


logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

current_dir = os.path.dirname(os.path.abspath(__file__))

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.websocket("/ws/connect/{user_id}")
async def websocket_connect(websocket: WebSocket, user_id: str):
    try:
        await connection_manager.connect(websocket, user_id)

    except HTTPException as e:
        logger.warning(f"Socket connection failed for user {user_id}: {e.detail}")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)


@app.websocket("/ws/{user_id}/{other_user_id}")
async def websocket_chat(websocket: WebSocket, user_id: str, other_user_id: str):
    try:
        await chat_manager.connect(websocket, user_id, other_user_id)

        while True:
            data: dict = await websocket.receive_json()

            if data.get("type") == "message":
                message = Message(**data.get("data"))
                await handle_send_chat_message(message)

    except HTTPException as e:
        logger.warning(f"Socket connection failed for user {user_id}: {e.detail}")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)

@app.post("/upload_files")
async def upload_files(
    request: Request,
    files: List[UploadFile] = File(...),
    chat_id: str = Form(...),
):
    try:
        current_user_id = request.state.user_id

        uploaded_files = [process_and_upload_file(file, chat_id) for file in files]
        logger.info(f"Uploaded {len(uploaded_files)} file(s) for chat {chat_id}")

        return {
            "success": True,
            "message": f"{len(uploaded_files)} file(s) uploaded successfully",
            "data": {
                "files": uploaded_files,
            },
        }

    except ValueError as ve:
        logger.error(f"Validation error during file upload: {str(ve)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))

    except Exception:
        logger.exception(
            f"Unexpected error during file upload for users {current_user_id} and {chat_id}"
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


@app.post("/get_attachment_urls")
async def get_presigned_urls(request: Request):
    try:
        data = await request.json()
        file_names = data.get("file_names")
        if not file_names:
            raise ValueError("No file names provided")
        return generate_presigned_urls(file_names)

    except ValueError as ve:
        logger.error(f"Validation error during file upload: {str(ve)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))


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

    uvicorn.run(app, host="0.0.0.0", port=3000)
