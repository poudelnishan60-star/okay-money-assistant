"""FastAPI entry point. Routers for transactions, insights, budgets, goals, bills and chat
are added in later build steps. The generated OpenAPI spec (/openapi.json) is the API contract."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings

settings = get_settings()

app = FastAPI(
    title="Khalti O-Kay AI Assistant API",
    version="0.1.0",
    description="Prototype backend for the O-Kay financial assistant. Mock data only.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    return {"status": "ok"}
