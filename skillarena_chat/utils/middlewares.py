from typing import List

from fastapi import Request
from fastapi.responses import JSONResponse
from jose import ExpiredSignatureError, JWTError, jwt
from starlette.middleware.base import BaseHTTPMiddleware

from skillarena_chat.config import config


class AuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, exempt_routes: List[str]):
        super().__init__(app)
        self.exempt_routes = exempt_routes

    async def dispatch(self, request: Request, call_next):
        if request.url.path in self.exempt_routes:
            return await call_next(request)

        token = request.headers.get("authorization")

        if not token:
            return await call_next(request)
            # !Do not allow unauthenticated access, Change this to return a 401 response
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing Authorization header"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        try:
            token = token.split("Bearer ")[1].strip()
            decoded = jwt.decode(
                token, config.ACCESS_TOKEN_SECRET, algorithms=[config.ALGORITHM]
            )
            user_id = decoded.get("_id")

            if user_id is None:
                raise JWTError("User ID not found in token")

            request.state.user_id = user_id

        except ExpiredSignatureError:
            return JSONResponse(
                status_code=401,
                content={"detail": "Token has expired"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        except JWTError:
            return JSONResponse(
                status_code=401,
                content={"detail": "Could not validate credentials"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        response = await call_next(request)
        return response
