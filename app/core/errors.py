import logging
from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("app.errors")


def http_exception_handler(request: Request, exc: StarletteHTTPException):
    # Safe to return exc.detail (it’s intended for clients), but don’t log secrets.
    logger.info("HTTPException %s path=%s", exc.status_code, request.url.path)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


def validation_exception_handler(request: Request, exc: RequestValidationError):
    # Don’t return internal validation structures if you want to keep it minimal.
    logger.info("ValidationError path=%s", request.url.path)
    return JSONResponse(status_code=422, content={"detail": "Invalid request"})


def unhandled_exception_handler(request: Request, exc: Exception):
    # Log stack trace server-side, but return generic message client-side.
    logger.exception("UnhandledException path=%s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})
