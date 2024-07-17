from exponent_server_sdk import (
    DeviceNotRegisteredError,
    PushClient,
    PushMessage,
    PushServerError,
    PushTicketError,
)
import os
import requests
from requests.exceptions import ConnectionError, HTTPError
from fastapi import HTTPException

# Optionally providing an access token within a session if you have enabled push security
session = requests.Session()
session.headers.update(
    {
        "Authorization": f"Bearer {os.getenv('EXPO_TOKEN')}",
        "accept": "application/json",
        "accept-encoding": "gzip, deflate",
        "content-type": "application/json",
    }
)


async def send_push_message(token: str, message: str, extra: dict = None):
    try:
        response = PushClient(session=session).publish(
            PushMessage(to=token, body=message, data=extra)
        )
    except PushServerError as exc:
        # Encountered some likely formatting/validation error.
        error_data = {
            "token": token,
            "message": message,
            "extra": extra,
            "errors": exc.errors,
            "response_data": exc.response_data,
        }
        raise HTTPException(status_code=500, detail=f"Push Server Error: {error_data}")
    except (ConnectionError, HTTPError) as exc:
        # Encountered some Connection or HTTP error
        error_data = {"token": token, "message": message, "extra": extra}
        raise HTTPException(
            status_code=503, detail=f"Connection or HTTP Error: {str(exc)}"
        )

    try:
        # We got a response back, but we don't know whether it's an error yet.
        # This call raises errors so we can handle them with normal exception flows.
        response.validate_response()
    except DeviceNotRegisteredError:
        # Mark the push token as inactive
        # Note: You'll need to implement this part based on your database setup
        # await mark_push_token_inactive(token)
        raise HTTPException(status_code=410, detail=f"Device Not Registered: {token}")
    except PushTicketError as exc:
        # Encountered some other per-notification error.
        error_data = {
            "token": token,
            "message": message,
            "extra": extra,
            "push_response": exc.push_response._asdict(),
        }
        raise HTTPException(status_code=500, detail=f"Push Ticket Error: {error_data}")

    return {"success": True, "response": response._asdict()}
