import logging
import httpx
from typing import Optional
from app.config import settings

logger = logging.getLogger(__name__)

# Toast auth token is cached here — refreshed when expired
_auth_token: Optional[str] = None


async def get_auth_token() -> str:
    """Fetch a fresh OAuth token from Toast."""
    global _auth_token
    url = f"{settings.toast_api_base}/authentication/v1/authentication/login"
    payload = {
        "clientId": settings.toast_client_id,
        "clientSecret": settings.toast_client_secret,
        "userAccessType": "TOAST_MACHINE_CLIENT",
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        _auth_token = data["token"]["accessToken"]
        logger.info("Toast auth token refreshed")
        return _auth_token


async def get_menu_items() -> list[dict]:
    """
    Pull all menu items from Toast with their SKUs and stock quantities.
    Returns a flat list of dicts with keys: toast_guid, sku, name, quantity.

    NOTE: Toast's inventory quantity lives under the stock endpoint.
    We fetch menu items first for the ID/SKU map, then stock separately.
    """
    token = await get_auth_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Toast-Restaurant-External-ID": settings.toast_restaurant_guid,
    }

    async with httpx.AsyncClient(timeout=60) as client:
        # Step 1: Get all menu items (for GUID → SKU mapping)
        menu_resp = await client.get(
            f"{settings.toast_api_base}/menus/v2/menus",
            headers=headers,
        )
        menu_resp.raise_for_status()
        menu_items = menu_resp.json()

        # Step 2: Get stock levels
        stock_resp = await client.get(
            f"{settings.toast_api_base}/stock/v1/inventory",
            headers=headers,
        )
        stock_resp.raise_for_status()
        stock_data = stock_resp.json()

    # Build a map of guid → quantity from stock response
    stock_map: dict[str, float] = {}
    for item in stock_data:
        guid = item.get("guid") or item.get("stockItem", {}).get("guid")
        qty = item.get("quantity", 0) or 0
        if guid:
            stock_map[guid] = qty

    # Combine menu items with stock quantities
    results = []
    for item in menu_items:
        guid = item.get("guid", "")
        sku = item.get("sku", "") or item.get("plu", "")
        name = item.get("name", "")
        quantity = stock_map.get(guid, 0)

        if not sku:
            logger.debug(f"Skipping Toast item with no SKU: {name} ({guid})")
            continue

        results.append({
            "toast_guid": guid,
            "sku": sku.strip(),
            "name": name,
            "quantity": int(quantity),
        })

    logger.info(f"Toast: fetched {len(results)} items with SKUs")
    return results
