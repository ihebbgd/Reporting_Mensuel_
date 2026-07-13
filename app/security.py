"""Authenticate before multipart parsing and cap streamed request bodies."""

import asyncio
import secrets
import tempfile

from fastapi import HTTPException, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.responses import JSONResponse

bearer = HTTPBearer(auto_error=False)


def authorize(request: Request, credential: HTTPAuthorizationCredentials | None = Security(bearer)):
    if credential is None or not secrets.compare_digest(
        credential.credentials.encode(), request.app.state.access_key.encode()
    ):
        raise HTTPException(401, "Clé d'accès incorrecte.", headers={"WWW-Authenticate": "Bearer"})


class AccessMiddleware:
    def __init__(self, app, config):
        self.app, self.config = app, config

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        path = scope["path"]
        public = path in (
            "/",
            "/health",
            "/docs",
            "/openapi.json",
            "/docs/oauth2-redirect",
        ) or path.startswith("/assets/")
        headers = dict(scope["headers"])

        async def secure_send(message):
            if message["type"] == "http.response.start":
                message.setdefault("headers", []).extend(
                    [
                        (b"x-content-type-options", b"nosniff"),
                        (b"x-frame-options", b"DENY"),
                        (b"referrer-policy", b"no-referrer"),
                        (b"cache-control", b"no-store"),
                    ]
                )
                if path == "/":
                    message["headers"].append(
                        (
                            b"content-security-policy",
                            b"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob: data:; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'",
                        )
                    )
            await send(message)

        if not public:
            expected = f"Bearer {scope['app'].state.access_key}".encode()
            if not secrets.compare_digest(headers.get(b"authorization", b""), expected):
                return await JSONResponse(
                    {"detail": "Clé d'accès incorrecte."},
                    401,
                    headers={"WWW-Authenticate": "Bearer"},
                )(scope, receive, secure_send)
        if path != "/upload" or scope["method"] != "POST":
            return await self.app(scope, receive, secure_send)
        limit = self.config.max_upload_size_mb * 1024 * 1024 + 65536
        try:
            length = int(headers.get(b"content-length", b"0"))
        except ValueError:
            return await JSONResponse({"detail": "Taille de requête invalide."}, 400)(
                scope, receive, secure_send
            )
        if length > limit:
            return await JSONResponse({"detail": "Fichier trop volumineux."}, 413)(
                scope, receive, secure_send
            )
        # Bound memory as well as disk consumption, even without Content-Length.
        with tempfile.SpooledTemporaryFile(max_size=1024 * 1024) as body:
            total = 0
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                chunk = message.get("body", b"")
                total += len(chunk)
                if total > limit:
                    return await JSONResponse({"detail": "Fichier trop volumineux."}, 413)(
                        scope, receive, secure_send
                    )
                await asyncio.to_thread(body.write, chunk)
                if not message.get("more_body", False):
                    break
            body.seek(0)

            async def replay():
                chunk = await asyncio.to_thread(body.read, 65536)
                return {"type": "http.request", "body": chunk, "more_body": body.tell() < total}

            await self.app(scope, replay, secure_send)
