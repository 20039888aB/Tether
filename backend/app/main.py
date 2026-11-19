import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import router as auth_router
from app.api.clinic_management import router as clinic_management_router
from app.api.health import router as health_router
from app.api.patient_access import router as patient_access_router
from app.api.system_sync import router as system_sync_router
from app.core.config import get_settings
from app.db.session import get_engine

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    engine = get_engine()
    if engine is not None:
        await engine.dispose()


settings = get_settings()
app = FastAPI(
    title="TETHER API",
    version="0.1.0",
    description="API foundation for a modular hospital management system.",
    lifespan=lifespan,
    docs_url="/docs" if settings.environment.lower() == "development" else None,
    redoc_url="/redoc" if settings.environment.lower() == "development" else None,
    openapi_url="/openapi.json" if settings.environment.lower() == "development" else None,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "X-CSRF-Token"],
)
app.include_router(health_router, prefix="/api/v1")
app.include_router(auth_router, prefix="/api/v1")
app.include_router(patient_access_router, prefix="/api/v1")
app.include_router(clinic_management_router, prefix="/api/v1")
app.include_router(system_sync_router, prefix="/api/v1")
