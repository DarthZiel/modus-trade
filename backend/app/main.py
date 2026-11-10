from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette.middleware.body_limit import RequestBodyLimitMiddleware

from app.ai import router as ai_router
from app.appeals import router as appeals_router
from app.auth import router
from app.database import engine
from app.discussion import router as discussion_router
from app.experiments import router as experiments_router
from app.feedback import router as feedback_router
from app.notifications import router as notifications_router
from app.similar import router as similar_router
from app.metrics import router as metrics_router
from app.telegram import internal as bot_router
from app.telegram import router as telegram_router
from app.uploads import MAX_BODY_SIZE
from app.work_queue import router as work_router
from app.similarities import router as similarities_router
from app.statistics import router as statistics_router
from app.priorities import router as priorities_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    engine.dispose()


app = FastAPI(title="Modus Feedback API", version="0.1.0", lifespan=lifespan)

app.include_router(router)
app.include_router(similar_router)
app.include_router(appeals_router)
app.include_router(work_router)
app.include_router(metrics_router)
app.include_router(discussion_router)
app.include_router(feedback_router)
app.include_router(notifications_router)
app.include_router(telegram_router)
app.include_router(bot_router)
app.include_router(ai_router)
app.include_router(experiments_router)
app.include_router(similarities_router)
app.include_router(statistics_router)
app.include_router(priorities_router)
app.add_middleware(RequestBodyLimitMiddleware, max_body_size=MAX_BODY_SIZE)


@app.middleware("http")
async def protect_requests(request: Request, call_next):
    # Custom header forces cross-origin browsers to preflight; no CORS origins are allowed.
    if (
        request.method in {"POST", "PUT", "PATCH", "DELETE"}
        and request.headers.get("X-Modus-Request") != "1"
    ):
        return JSONResponse(
            status_code=403,
            content={"detail": "Отсутствует защитный заголовок запроса"},
        )
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    database: Literal["connected", "unavailable"]


@app.get("/health", tags=["System"])
def health(response: Response) -> HealthResponse:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        response.status_code = 503
        return HealthResponse(status="degraded", database="unavailable")
    return HealthResponse(status="ok", database="connected")
