from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from ttc.api.v1.router import router as v1_router
from ttc.core.config import get_settings
from ttc.core.db import dispose_engine
from ttc.core.errors import TTCError
from ttc.core.request_context import request_id_context


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    await dispose_engine()


settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)


@app.middleware("http")
async def attach_request_id(request: Request, call_next):
    supplied_id = request.headers.get("X-Request-Id", "").strip()
    request_id = supplied_id[:128] if supplied_id else str(uuid4())
    token = request_id_context.set(request_id)
    try:
        response = await call_next(request)
        response.headers["X-Request-Id"] = request_id
        return response
    finally:
        request_id_context.reset(token)


@app.exception_handler(TTCError)
async def handle_ttc_error(request: Request, exc: TTCError) -> JSONResponse:
    request_id = request_id_context.get()
    return JSONResponse(
        status_code=exc.status_code,
        content=jsonable_encoder({
            "code": exc.code,
            "message": exc.message,
            "request_id": request_id,
            "details": exc.details,
        }),
        headers={"X-Request-Id": request_id},
    )


@app.exception_handler(RequestValidationError)
async def handle_validation_error(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    request_id = request_id_context.get()
    return JSONResponse(
        status_code=422,
        content={
            "code": "TTC-4000",
            "message": "请求参数校验失败",
            "request_id": request_id,
            "details": {"errors": exc.errors()},
        },
        headers={"X-Request-Id": request_id},
    )


app.include_router(v1_router, prefix=settings.api_prefix)


@app.get("/", include_in_schema=False)
async def root() -> dict[str, str]:
    return {"service": "ttc-api", "docs": "/docs"}
