import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.routers.auth import router as auth_router
from app.routers.me import router as me_router
from app.routers.interests import router as interests_router
from app.routers.targets import router as targets_router
from app.routers.exports import router as exports_router
from app.routers.admin import router as admin_router
from app.routers.webhooks import router as webhooks_router
from app.routers.stripe_checkout import router as stripe_router

from app.core.logging import configure_logging, new_request_id, request_id_ctx
from app.core.errors import (
    http_exception_handler,
    validation_exception_handler,
    unhandled_exception_handler,
)

configure_logging()
logger = logging.getLogger("app")


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("x-request-id") or new_request_id()
        token = request_id_ctx.set(rid)
        try:
            response = await call_next(request)
            response.headers["x-request-id"] = rid
            return response
        finally:
            request_id_ctx.reset(token)


app = FastAPI(title="Polymath Focus API")
app.add_middleware(RequestIdMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(auth_router)
app.include_router(me_router)
app.include_router(interests_router)
app.include_router(targets_router)
app.include_router(exports_router)
app.include_router(admin_router)
app.include_router(webhooks_router)
app.include_router(stripe_router)


app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/")
def root():
    return {"status": "ok", "docs": "/docs"}
