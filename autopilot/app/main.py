"""Autopilot for Small Trades — FastAPI application.

Run locally:
    cd autopilot
    uvicorn app.main:app --reload --port 8000

The whole product works with every integration in dry-run mode, so this boots
with no keys at all. Add Twilio / Stripe / Vapi credentials to go live.
"""
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.orm import Session

from .config import settings
from .db import engine, get_db, init_db
from .plans import plan_list
from .prompt import build_system_prompt
from .routers import admin, auth, payments, sms, voice
from .security import verify_cron_secret
from .services import scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("autopilot")

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    log.info("Database ready (%s)", "sqlite" if str(engine.url).startswith("sqlite") else "postgres")
    if settings.demo_mode and os.getenv("AUTO_SEED_DEMO", "1") == "1":
        try:
            from .seed import seed_demo

            seed_demo()
        except Exception as exc:
            log.warning("Demo seed skipped: %s", exc)
    if settings.enable_scheduler:
        scheduler.start_background_loop(settings.scheduler_interval_seconds)
    log.info(
        "Integrations — sms:%s payments:%s voice:%s",
        "dry-run" if settings.sms_dry_run else "twilio",
        "dry-run" if settings.payments_dry_run else "stripe",
        "live" if settings.vapi_api_key else "dry-run",
    )
    yield


app = FastAPI(
    title="Autopilot for Small Trades",
    version="0.1.0",
    description=(
        "Phone-first admin autopilot for small Canadian trade businesses: "
        "answers calls, books jobs, invoices, chases payment, asks for reviews, "
        "and rebooks."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8000",
        "http://localhost:5173",
        settings.base_url,
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/pay/thanks", include_in_schema=False)
def pay_thanks():
    """Registered before the payments router so /pay/{invoice_id} cannot shadow it."""
    page = STATIC_DIR / "thanks.html"
    if page.exists():
        return FileResponse(page)
    return JSONResponse({"ok": True, "message": "Payment received. Thank you."})


app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(voice.router)
app.include_router(sms.router)
app.include_router(payments.router)

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/health", tags=["system"])
def health(db: Session = Depends(get_db)):
    database = "ok"
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        database = f"error: {exc.__class__.__name__}"
    return {
        "status": "ok" if database == "ok" else "degraded",
        "environment": settings.environment,
        "database": database,
        "integrations": {
            "sms": "dry_run" if settings.sms_dry_run else "twilio",
            "payments": "dry_run" if settings.payments_dry_run else "stripe",
            "voice": "dry_run" if not settings.vapi_api_key else "vapi",
        },
        "scheduler": "enabled" if settings.enable_scheduler else "disabled",
        "demo_mode": settings.demo_mode,
    }


@app.post("/internal/run-scheduler", tags=["system"])
def run_scheduler(
    business_id: str | None = None,
    x_cron_secret: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    """Railway cron target. Protect with CRON_SECRET in production."""
    if not verify_cron_secret(x_cron_secret, authorization):
        raise HTTPException(401, "Bad cron secret")
    return scheduler.run_due_tasks(db, business_id)


@app.get("/internal/businesses/{business_id}/prompt", tags=["system"])
def business_prompt(
    business_id: str,
    x_cron_secret: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    if not verify_cron_secret(x_cron_secret):
        raise HTTPException(401, "Bad cron secret")
    from . import models

    business = db.get(models.Business, business_id)
    if business is None:
        raise HTTPException(404, "Business not found")
    return {"system_prompt": build_system_prompt(business)}


@app.get("/api/plans")
def plans():
    return {"plans": plan_list()}


@app.get("/", include_in_schema=False)
def index():
    index_file = STATIC_DIR / "index.html"
    if not index_file.exists():
        return JSONResponse({"app": "Autopilot for Small Trades", "docs": "/docs"})
    return FileResponse(index_file)


@app.exception_handler(404)
async def not_found(request: Request, exc):
    if request.url.path.startswith(("/api", "/webhooks", "/internal")):
        return JSONResponse({"detail": "Not found"}, status_code=404)
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return JSONResponse({"detail": "Not found"}, status_code=404)
