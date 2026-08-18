from contextlib import asynccontextmanager
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.api.deps import get_engine
from app.api.investment_routes import router as investment_router
from app.api.routes import router
from app.core.config import get_settings
from app.investment.demo_seed import bootstrap_investment_demo
from app.investment.users import get_user_registry

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


def _bootstrap_investment_admin() -> None:
    settings = get_settings()
    email = (settings.invest_admin_email or "").strip()
    password = settings.invest_admin_password or ""
    if not email or not password:
        return
    try:
        users = get_user_registry()
        users.ensure_admin(
            email=email,
            password=password,
            full_name=settings.invest_admin_name,
        )
    except Exception:  # noqa: BLE001
        log.exception("investment admin bootstrap failed")


@asynccontextmanager
async def lifespan(_: FastAPI):
    _bootstrap_database()
    _bootstrap_investment_admin()
    bootstrap_investment_demo()
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
    app.include_router(investment_router, prefix=settings.api_prefix)

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

        @app.get("/")
        async def spa_index() -> FileResponse:
            return FileResponse(static_dir / "index.html")

    return app


app = create_app()
