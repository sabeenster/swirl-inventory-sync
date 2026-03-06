import logging
import asyncio
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from app.config import settings

logger = logging.getLogger(__name__)

SHOPIFY_API_VERSION = "2024-10"


def _base_url() -> str:
    return f"https://{settings.shopify_store_domain}/admin/api/{SHOPIFY_API_VERSION}"


def _headers() -> dict:
    return {
        "X-Shopify-Access-Token": settings.shopify_access_token,
        "Content-Type": "application/json",
    }


async def _handle_rate_limit(resp: httpx.Response) -> None:
    """Check Shopify rate limit headers and sleep if we're close to the limit."""
    call_limit = resp.headers.get("X-Shopify-Shop-Api-Call-Limit", "")
    if "/" in call_limit:
        used, total = call_limit.split("/")
        remaining = int(total) - int(used)
        if remaining < 5:
            wait_time = 2.0
            logger.warning(f"Shopify rate limit close ({used}/{total}), pausing {wait_time}s")
            await asyncio.sleep(wait_time)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=30),
    retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.ConnectError, httpx.ReadTimeout)),
    reraise=True,
)
async def get_all_variants() -> list[dict]:
    """
    Fetch all product variants from Shopify with their SKUs and inventory_item_ids.
    Handles pagination automatically.
    Returns list of dicts: shopify_variant_id, inventory_item_id, sku, title.
    """
    variants = []
    url = f"{_base_url()}/products.json"
    params = {"limit": 250, "fields": "id,title,variants"}

    async with httpx.AsyncClient(timeout=60) as client:
        while url:
            resp = await client.get(url, headers=_headers(), params=params)

            # Handle 429 rate limiting explicitly
            if resp.status_code == 429:
                retry_after = float(resp.headers.get("Retry-After", "2"))
                logger.warning(f"Shopify 429 rate limited, waiting {retry_after}s")
                await asyncio.sleep(retry_after)
                continue

            resp.raise_for_status()
            await _handle_rate_limit(resp)
            data = resp.json()

            for product in data.get("products", []):
                for variant in product.get("variants", []):
                    sku = variant.get("sku", "").strip()
                    if not sku:
                        continue
                    variants.append({
                        "shopify_variant_id": variant["id"],
                        "inventory_item_id": variant["inventory_item_id"],
                        "sku": sku,
                        "title": f"{product['title']} — {variant.get('title', '')}",
                    })

            # Handle Shopify pagination via Link header
            link_header = resp.headers.get("Link", "")
            next_url = None
            if 'rel="next"' in link_header:
                for part in link_header.split(","):
                    if 'rel="next"' in part:
                        next_url = part.split(";")[0].strip().strip("<>")
            url = next_url
            params = {}  # page_info is embedded in next_url

    logger.info(f"Shopify: fetched {len(variants)} variants with SKUs")
    return variants


async def set_inventory_level(inventory_item_id: int, quantity: int) -> bool:
    """Set absolute inventory quantity for an item at Swirl's location."""
    if settings.dry_run:
        logger.info(f"[DRY RUN] Would set inventory_item {inventory_item_id} → {quantity}")
        return True

    url = f"{_base_url()}/inventory_levels/set.json"
    payload = {
        "location_id": int(settings.shopify_location_id),
        "inventory_item_id": inventory_item_id,
        "available": quantity,
    }

    async with httpx.AsyncClient(timeout=30) as client:
        for attempt in range(3):
            resp = await client.post(url, headers=_headers(), json=payload)

            if resp.status_code == 429:
                retry_after = float(resp.headers.get("Retry-After", "2"))
                logger.warning(f"Shopify 429 on inventory set, waiting {retry_after}s")
                await asyncio.sleep(retry_after)
                continue

            if resp.status_code == 200:
                return True
            else:
                logger.error(
                    f"Shopify inventory set failed for item {inventory_item_id} "
                    f"(attempt {attempt + 1}/3): {resp.status_code} {resp.text}"
                )

        return False
