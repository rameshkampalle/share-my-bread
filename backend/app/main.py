import uuid
import logging
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.shared.config import get_settings
from app.api.cart import router as cart_router
from app.api.journey import router as journey_router
from app.api.workspace import router as workspace_router
from app.api.notifications import router as notifications_router
from app.api.operations import router as operations_router

settings = get_settings()
logger = logging.getLogger("share_my_bread")
app = FastAPI(title=settings.app_name, version=settings.app_version)
app.include_router(cart_router)
app.include_router(journey_router)
app.include_router(workspace_router)
app.include_router(notifications_router)
app.include_router(operations_router)

if settings.allowed_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Correlation-Id"],
    )


@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    correlation_id = request.headers.get("X-Correlation-Id") or str(uuid.uuid4())
    request.state.correlation_id = correlation_id
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("Unhandled request failure correlation_id=%s", correlation_id)
        response = JSONResponse(
            status_code=500,
            content={
                "code": "INTERNAL_ERROR",
                "message": "The request could not be completed.",
                "correlationId": correlation_id,
            },
        )
    response.headers["X-Correlation-Id"] = correlation_id
    return response


@app.get("/health", tags=["operations"])
async def health():
    return {
        "status": "ok",
        "service": settings.app_name,
        "version": settings.app_version,
        "environment": settings.app_env,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "features": {
            "aiAssistant": settings.ai_assistant_enabled,
            "semanticSearch": settings.semantic_search_enabled,
            "retailerMode": settings.retailer_integration_mode,
            "paymentMode": settings.payment_mode,
        },
    }
