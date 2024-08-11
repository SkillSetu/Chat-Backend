# Skillarena Chat API Documentation

## Overview

This API provides a real-time chat system with WebSocket support, user authentication, chat history retrieval, and file uploading capabilities.

## Authentication

Most routes require authentication using a bearer token via the `authorization` header.

## Endpoints

### 1. WebSocket Connection

- **URL:** `/ws/{token}`
- **Method:** WebSocket
- **Description:** Establishes a WebSocket connection for real-time messaging.
- **Authentication:** Required (via token in URL)

> Note: Only here the token is passed in the URL.

### 2. Get Chat History

- **URL:** `/chat_history/{other_user_id}`
- **Method:** GET
- **Description:** Retrieves chat history with a specific user.
- **Authentication:** Required
- **Response:** Array of message objects

### 3. Get All User Chats

- **URL:** `/chat_history`
- **Method:** GET
- **Description:** Retrieves all chats for the authenticated user.
- **Authentication:** Required
- **Response:** Array of chat objects

### 4. Upload Files

- **URL:** `/upload_files`
- **Method:** POST
- **Description:** Uploads files to a specific chat.
- **Authentication:** Required
- **Parameters:**
  - `files`: List of files (multipart/form-data)
  - `other_user_id`: String (form data)
- **Response:** JSON object with upload status and file details

### 5. Get Presigned URLs

- **URL:** `/get_presigned_urls`
- **Method:** POST
- **Description:** Gets presigned URLs for files in a specific chat message.
- **Authentication:** Required
- **Parameters:**
  - `files`: List of file names (JSON)
- **Response:** JSON object with presigned URLs

## WebSocket Message Format

There can be two types of messages: `message` and `receipt_update`.

For `message`:

```json
{
  "type": "message",
  "data": {
    "sender_id": "user_id",
    "receiver_id": "user_id",
    "status": "sent | delivered | read",
    "message": "message_text",
    "attachments": ["file_url"],
    "created_at": "timestamp"
  }
}
```

For `receipt_update`:

```json
{
  "type": "receipt_update",
  "data": {
    "chat_id": "chat_id",
    "user_id": "receiver_id",
    "message_id": "message_id",
    "status": "delivered | read",
    "stop": "true | false" // Sent via the front-end to stop the receipt update loop
  }
}
```
