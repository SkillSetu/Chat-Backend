import os

import requests
from exponent_server_sdk import (
    DeviceNotRegisteredError,
    PushClient,
    PushMessage,
    PushServerError,
    PushTicketError,
)
from fastapi import HTTPException
from requests.exceptions import ConnectionError, HTTPError

from ..db.database import db


session = requests.Session()
session.headers.update(
    {
        "Authorization": f"Bearer {os.getenv('EXPO_TOKEN')}",
        "accept": "application/json",
        "accept-encoding": "gzip, deflate",
        "content-type": "application/json",
    }
)


async def send_push_message(client_id: str, message: str, extra: dict = None):
    token = await get_push_token(client_id)

    try:
        response = PushClient(session=session).publish(
            PushMessage(to=token, body=message, data=extra)
        )
    except PushServerError as exc:
        error_data = {
            "token": token,
            "message": message,
            "extra": extra,
            "errors": exc.errors,
            "response_data": exc.response_data,
        }

        raise HTTPException(status_code=500, detail=f"Push Server Error: {error_data}")

    except (ConnectionError, HTTPError) as exc:
        error_data = {"token": token, "message": message, "extra": extra}
        raise HTTPException(
            status_code=503, detail=f"Connection or HTTP Error: {str(exc)}"
        )

    try:
        response.validate_response()

    except DeviceNotRegisteredError:
        raise HTTPException(status_code=410, detail=f"Device Not Registered: {token}")

    except PushTicketError as exc:
        error_data = {
            "token": token,
            "message": message,
            "extra": extra,
            "push_response": exc.push_response._asdict(),
        }

        raise HTTPException(status_code=500, detail=f"Push Ticket Error: {error_data}")

    return {"success": True, "response": response._asdict()}


async def get_push_token(client_id: str):
    try:
        user = await db.users.find_one({"_id": client_id})
        if user.get("notificationPermissionToken"):
            return user.get("notificationPermissionToken")
        else:
            raise HTTPException(
                status_code=404, detail=f"Push token not found for {client_id}"
            )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching user: {str(e)}")
