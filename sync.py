import logging
import math
from datetime import datetime
from app.toast_client import get_menu_items
from app.shopify_client import get_all_variants, set_inventory_level
from app.config import settings
from app.email_alerts import send_sync_summary

logger = logging.getLogger(__name__)


async def run_sync() -> dict:
    """
    Main sync logic:
    1. Pull inventory from Toast
    2. Pull variants from Shopify
    3. Match on SKU
    4. Apply buffer and push quantities to Shopify
    5. Send email summary
    """
    started_at = datetime.utcnow()
    logger.info("=== Starting Toast → Shopify inventory sync ===")

    # --- Fetch from both systems ---
    toast_items = await get_menu_items()
    shopify_variants = await get_all_variants()

    # Build SKU → Shopify variant map
    shopify_by_sku: dict[str, dict] = {v["sku"]: v for v in shopify_variants}

    # --- Match and sync ---
    updated = []
    skipped_no_match = []
    skipped_zero = []
    errors = []

    for item in toast_items:
        sku = item["sku"]
        toast_qty = item["quantity"]

        if sku not in shopify_by_sku:
            skipped_no_match.append({"sku": sku, "name": item["name"]})
            continue

        shopify_variant = shopify_by_sku[sku]

        # Apply inventory buffer — hold back a % to avoid oversells
        # e.g. 10 bottles in Toast → show 9 on Shopify
        buffered_qty = math.floor(toast_qty * (1 - settings.inventory_buffer_pct))
        buffered_qty = max(0, buffered_qty)

        if toast_qty == 0:
            skipped_zero.append({"sku": sku, "name": item["name"]})
            # Still update Shopify to 0 so it goes out of stock correctly
            buffered_qty = 0

        success = await set_inventory_level(
            inventory_item_id=shopify_variant["inventory_item_id"],
            quantity=buffered_qty,
        )

        if success:
            updated.append({
                "sku": sku,
                "name": item["name"],
                "toast_qty": toast_qty,
                "shopify_qty": buffered_qty,
            })
        else:
            errors.append({"sku": sku, "name": item["name"]})

    finished_at = datetime.utcnow()
    duration_s = (finished_at - started_at).total_seconds()

    result = {
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_seconds": duration_s,
        "dry_run": settings.dry_run,
        "summary": {
            "toast_items_fetched": len(toast_items),
            "shopify_variants_fetched": len(shopify_variants),
            "updated": len(updated),
            "skipped_no_sku_match": len(skipped_no_match),
            "skipped_zero_stock": len(skipped_zero),
            "errors": len(errors),
        },
        "updated_items": updated,
        "unmatched_skus": skipped_no_match,
        "errors": errors,
    }

    logger.info(
        f"Sync complete in {duration_s:.1f}s — "
        f"updated={len(updated)}, unmatched={len(skipped_no_match)}, errors={len(errors)}"
    )

    # Send email summary (same Resend pattern as wine enrichment agent)
    await send_sync_summary(result)

    return result
