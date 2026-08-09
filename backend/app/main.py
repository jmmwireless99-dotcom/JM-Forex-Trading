from contextlib import asynccontextmanager
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.api.deps import get_engine
from app.api.routes import router
from app.core.config import get_settings

log = logging.getLogger(__name__)


def _bootstrap_database() -> None:
    """Optional Postgres migrate + seed — never blocks desk if DB is down."""
    settings = get_settings()
    if not (settings.database_url or "").strip():
        return
    try:
        from app.db.session import ping_db

        health = ping_db()
        if not health.get("ok"):
            log.warning("database not reachable: %s", health.get("error"))
            return
        if settings.database_auto_migrate:
            from alembic import command
            from alembic.config import Config
            from pathlib import Path as P

            ini = P(__file__).resolve().parents[1] / "alembic.ini"
            cfg = Config(str(ini))
            command.upgrade(cfg, "head")
            log.info("alembic upgrade head OK")
        if settings.database_seed_on_boot:
            from app.db.seed import seed_strategies

            result = seed_strategies(force_update=True)
            log.info("strategy seed: %s", result)
    except Exception:  # noqa: BLE001
        log.exception("database bootstrap failed — continuing without DB")


@asynccontextmanager
async def lifespan(_: FastAPI):
    _bootstrap_database()
    # Auto-start paper engine so the dashboard has live data immediately
    engine = get_engine()
    await engine.start()
    yield
    await engine.stop()


def _static_dir() -> Path | None:
    settings = get_settings()
    candidates = [
        Path(settings.static_dir) if settings.static_dir else None,
        Path(__file__).resolve().parents[2] / "static",
        Path(__file__).resolve().parents[2] / "frontend" / "dist",
    ]
    for path in candidates:
        if path and path.exists() and (path / "index.html").exists():
            return path
    return None


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        description="JM Forex trading platform automation — paper trading engine",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "https://jmtechsolution.cloud",
            "https://forex.jmtechsolution.cloud",
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "*",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router, prefix=settings.api_prefix)

    static_dir = _static_dir()
    if static_dir is not None:
        assets = static_dir / "assets"
        if assets.exists():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        favicon = static_dir / "favicon.svg"
        if favicon.exists():

            @app.get("/favicon.svg")
            async def favicon_svg() -> FileResponse:
                return FileResponse(favicon)

        downloads = static_dir / "downloads"
        if downloads.exists():

            @app.get("/downloads/{filename}")
            async def download_file(filename: str) -> FileResponse:
                # Bridge EA + other install helpers for Windows MT5 users.
                safe = Path(filename).name
                target = downloads / safe
                if not target.exists() or not target.is_file():
                    from fastapi import HTTPException

                    raise HTTPException(status_code=404, detail="File not found")
                return FileResponse(
                    target,
                    filename=safe,
                    media_type="application/octet-stream",
                )

        @app.get("/")
        async def spa_index() -> FileResponse:
            return FileResponse(static_dir / "index.html")

    return app


app = create_app()
