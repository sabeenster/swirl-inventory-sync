import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Run at 6am and 6pm PT (14:00 and 02:00 UTC)
    scheduler.add_job(
        run_sync,
        CronTrigger(hour="2,14", minute="0", timezone="UTC"),
        id="inventory_sync",
        name="Toast → Shopify Inventory Sync",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Scheduler started — syncing at 6am and 6pm PT")
    yield
    scheduler.shutdown()


app = FastAPI(
    title="Swirl Inventory Sync",
    description="Toast → Shopify inventory sync agent for Swirl on Castro",
    lifespan=lifespan,
)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/sync/trigger")
async def trigger_sync():
    """Manually trigger a sync — useful for testing or post-receiving."""
    logger.info("Manual sync triggered via API")
    result = await run_sync()
    return result
