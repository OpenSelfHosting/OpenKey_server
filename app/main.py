import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api import attachments, auth, collections, entries, orgs, shares, sync
from app.config import get_settings
from app.db.migrate import run_migrations
from app.db.session import engine
from app.docs import docs_router
from app.docs.openapi import API_VERSION, build_openapi_schema


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Validate settings (incl. JWT_SECRET) before accepting traffic.
    get_settings()
    # Run in a worker thread so Alembic's asyncio.run() does not nest in uvicorn's loop.
    await asyncio.to_thread(run_migrations)
    yield
    await engine.dispose()


settings = get_settings()

app = FastAPI(
    title="OpenKey Sync API",
    description=(
        "Zero-knowledge password manager sync API. "
        "The server stores ciphertext only and never decrypts vault data."
    ),
    version=API_VERSION,
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url="/openapi.json",
)


def custom_openapi():
    return build_openapi_schema(app)


app.openapi = custom_openapi  # type: ignore[method-assign]

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next) -> Response:
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault(
        "Permissions-Policy",
        "geolocation=(), microphone=(), camera=()",
    )
    # API responses must not be cached by shared intermediaries.
    if request.url.path.startswith(
        ("/auth", "/sync", "/collections", "/entries", "/attachments", "/orgs", "/invites", "/shares")
    ):
        response.headers.setdefault("Cache-Control", "no-store")
    return response


app.include_router(docs_router)
app.include_router(auth.router)
app.include_router(collections.router)
app.include_router(entries.router)
app.include_router(attachments.router)
app.include_router(orgs.router)
app.include_router(shares.router)
app.include_router(sync.router)


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    """Liveness + DB readiness. Returns 503 when Postgres is unreachable."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable",
        ) from exc
    return {"status": "ok", "database": "ok"}
