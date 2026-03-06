import logging
import httpx
from typing import Optional
from app.config import settings

logger = logging.getLogger(__name__)

_auth_token: Optional[str] = None


async def get_auth_token() -> str:
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
    Pull inventory from Toast stock API only.
    Returns list of dicts: toast_guid (=Shopify SKU), quantity.
    Only returns QUANTITY and OUT_OF_STOCK items.
    IN_STOCK items are not returned by this endpoint.
    """
    token = await get_auth_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Toast-Restaurant-External-ID": settings.toast_restaurant_guid,
    }

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.get(
            f"{settings.toast_api_base}/stock/v1/inventory",
            headers=headers,
        )
        resp.raise_for_status()
        stock_data = resp.json()

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
            "name": guid,  # no name from stock endpoint
            "quantity": int(quantity),
        })

    logger.info(f"Toast: {len(results)} items with tracked inventory")
    return results
