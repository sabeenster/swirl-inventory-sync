import logging
from contextlib import asynccontextmanager
from zoneinfo import ZoneInfo
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.sync import run_sync
from app.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()

# Store last sync result for /sync/status
_last_sync_result: dict | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    # DST-aware: uses America/Los_Angeles so 6am/6pm PT is always correct
    scheduler.add_job(
        _scheduled_sync,
        CronTrigger(hour="6,18", minute="0", timezone=ZoneInfo("America/Los_Angeles")),
        id="inventory_sync",
        name="Toast → Shopify Inventory Sync",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Scheduler started — syncing at 6am and 6pm PT (DST-aware)")
    yield
    scheduler.shutdown()


async def _scheduled_sync():
    """Wrapper for scheduled runs — catches errors so APScheduler doesn't choke."""
    global _last_sync_result
    try:
        _last_sync_result = await run_sync()
    except Exception as e:
        logger.exception(f"Scheduled sync failed: {e}")
        _last_sync_result = {"error": str(e), "status": "failed"}


app = FastAPI(
    title="Swirl Inventory Sync",
    description="Toast → Shopify inventory sync agent for Swirl on Castro",
    lifespan=lifespan,
)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/sync/status")
async def sync_status():
    """Return the result of the last sync without triggering a new one."""
    if _last_sync_result is None:
        return {"status": "no sync has run yet"}
    return _last_sync_result


@app.post("/sync/trigger")
async def trigger_sync():
    """Manually trigger a sync — useful for testing or post-receiving."""
    global _last_sync_result
    logger.info("Manual sync triggered via API")
    try:
        result = await run_sync()
        _last_sync_result = result
        return result
    except Exception as e:
        logger.exception(f"Sync failed: {e}")
        error_resp = {"error": str(e), "status": "failed"}
        _last_sync_result = error_resp
        return JSONResponse(status_code=500, content=error_resp)
