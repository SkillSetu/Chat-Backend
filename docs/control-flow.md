# Skillarena Chat API Documentation

## Websocket - Connect

```
ws://{{BASE_URL}}/ws/connect/{user_id}
```

- Maintains online status of users
- Fetches recipents list in the following format:

```json
{
  "type": "recipient_list",
  "data": {
    "chat_id": "66c0a9f8820d0e9f18db653c",
    "receiver": "66af7f527c91e266b47c4731",
    "name": "Shreyansh  Jain",
    "last_message": "Hello! My name is Chirag",
    "is_blocked": false,
    "last_updated": "2024-08-17T13:47:36.432000"
  }
}
```

<div style="page-break-after: always;"></div>

## Websocket - Chat

```
ws://{{BASE_URL}}/ws/{user_id}/{other_user_id}
```

- Sends and receives messages between users
- Send message in the following format:

```json
{
  "type": "message",
  "data": {
    "sender": "66bf2b9e3fce23d4019dee06",
    "receiver": "66be5593d8c3fedbb7d7ff14",
    "message": "Hello! My name is Chirag"
  }
}
```

- Receive message in the following format:

```json
{
  "type": "message",
  "data": {
    "id": "66bf6868b2d7aa887c3427b5",
    "sender": "66bf2b9e3fce23d4019dee06",
    "receiver": "66be5593d8c3fedbb7d7ff14",
    "status": "sent",
    "message": "Hello! My name is Chirag",
    "attachments": null,
    "created_at": "2024-08-16T14:55:36.326771"
  }
}
```
