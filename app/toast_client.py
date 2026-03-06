import logging
import time
import httpx
from typing import Optional
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from app.config import settings

logger = logging.getLogger(__name__)

# Token cache — avoids re-authing on every call
_auth_token: Optional[str] = None
_token_expires_at: float = 0  # epoch seconds


async def get_auth_token(force_refresh: bool = False) -> str:
    """Get a Toast auth token, reusing cached token if still valid."""
    global _auth_token, _token_expires_at

    # Reuse if token exists and has >60s remaining
    if _auth_token and not force_refresh and time.time() < (_token_expires_at - 60):
        return _auth_token

    url = f"{settings.toast_api_base}/authentication/v1/authentication/login"
    payload = {
        "clientId": settings.toast_client_id,
        "clientSecret": settings.toast_client_secret,
        "userAccessType": "TOAST_MACHINE_CLIENT",
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, json=payload)
        if resp.status_code == 401:
            raise ToastAuthError(
                f"Toast auth failed (401). Check your TOAST_CLIENT_ID and "
                f"TOAST_CLIENT_SECRET. Full response: {resp.text}"
            )
        resp.raise_for_status()
        data = resp.json()
        _auth_token = data["token"]["accessToken"]
        # Toast tokens typically last 12h; cache conservatively for 1h
        _token_expires_at = time.time() + 3600
        logger.info("Toast auth token refreshed")
        return _auth_token


def _toast_headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Toast-Restaurant-External-ID": settings.toast_restaurant_guid,
    }


class ToastAuthError(Exception):
    """Raised when Toast credentials are invalid or not yet activated."""
    pass


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=30),
    retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.ConnectError, httpx.ReadTimeout)),
    reraise=True,
)
async def _get_stock_data(token: str) -> list[dict]:
    """Fetch stock/inventory data from Toast with retries."""
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.get(
            f"{settings.toast_api_base}/stock/v1/inventory",
            headers=_toast_headers(token),
        )
        resp.raise_for_status()
        return resp.json()


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=30),
    retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.ConnectError, httpx.ReadTimeout)),
    reraise=True,
)
async def _get_menu_items_raw(token: str) -> list[dict]:
    """Fetch all menu items from Toast to resolve GUIDs → human-readable names."""
    all_items = []
    page_size = 100
    page = 0

    async with httpx.AsyncClient(timeout=60) as client:
        while True:
            resp = await client.get(
                f"{settings.toast_api_base}/menus/v2/menuItems",
                headers=_toast_headers(token),
                params={"pageSize": page_size, "page": page},
            )
            resp.raise_for_status()
            items = resp.json()

            if not items:
                break

            all_items.extend(items)
            if len(items) < page_size:
                break
            page += 1

    return all_items


async def get_menu_items() -> list[dict]:
    """
    Pull inventory from Toast stock API, then resolve names from menu items.
    Returns list of dicts: sku (= Toast GUID), name, quantity.
    """
    token = await get_auth_token()

    # 1. Fetch stock levels
    stock_data = await _get_stock_data(token)

    # 2. Fetch menu items to build GUID → name lookup
    try:
        menu_items = await _get_menu_items_raw(token)
        guid_to_name = {}
        for mi in menu_items:
            guid = mi.get("guid", "")
            name = mi.get("name", "")
            if guid and name:
                guid_to_name[guid] = name
        logger.info(f"Toast: resolved {len(guid_to_name)} menu item names")
    except Exception as e:
        logger.warning(f"Could not fetch menu item names (will use GUIDs): {e}")
        guid_to_name = {}

    # 3. Build results with resolved names
    results = []
    for item in stock_data:
        guid = item.get("guid", "")
        status = item.get("status", "")
        quantity = item.get("quantity") or 0

        if not guid:
            continue

        if status == "OUT_OF_STOCK":
            quantity = 0
        elif status == "IN_STOCK":
            continue  # not returned by endpoint but just in case

        results.append({
            "toast_guid": guid,
            "sku": guid,  # Shopify SKU = Toast GUID
            "name": guid_to_name.get(guid, guid),  # resolved name or fallback to GUID
            "quantity": int(quantity),
        })

    logger.info(f"Toast: {len(results)} items with tracked inventory")
    return results
