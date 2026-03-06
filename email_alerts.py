import logging
import httpx
from app.config import settings

logger = logging.getLogger(__name__)


def _build_email_html(result: dict) -> str:
    s = result["summary"]
    dry_run_badge = '<span style="background:#f59e0b;color:white;padding:2px 8px;border-radius:4px;font-size:12px;">DRY RUN</span>' if result["dry_run"] else ""

    unmatched_rows = ""
    if result["unmatched_skus"]:
        rows = "".join(
            f"<tr><td style='padding:4px 8px'>{i['sku']}</td><td style='padding:4px 8px'>{i['name']}</td></tr>"
            for i in result["unmatched_skus"][:50]  # cap at 50 in email
        )
        unmatched_rows = f"""
        <h3 style="color:#dc2626">Unmatched SKUs (Toast items with no Shopify match)</h3>
        <table border="1" cellspacing="0" style="border-collapse:collapse;font-size:13px">
          <tr style="background:#f3f4f6"><th style="padding:4px 8px">SKU</th><th style="padding:4px 8px">Name</th></tr>
          {rows}
        </table>
        <p style="font-size:12px;color:#6b7280">These SKUs exist in Toast but have no matching variant in Shopify. Add them to Shopify or update the SKU to match.</p>
        """

    error_rows = ""
    if result["errors"]:
        rows = "".join(
            f"<tr><td style='padding:4px 8px'>{i['sku']}</td><td style='padding:4px 8px'>{i['name']}</td></tr>"
            for i in result["errors"]
        )
        error_rows = f"""
        <h3 style="color:#dc2626">❌ Errors</h3>
        <table border="1" cellspacing="0" style="border-collapse:collapse;font-size:13px">
          <tr style="background:#f3f4f6"><th style="padding:4px 8px">SKU</th><th style="padding:4px 8px">Name</th></tr>
          {rows}
        </table>
        """

    return f"""
    <div style="font-family:sans-serif;max-width:600px;margin:0 auto">
      <h2>🍷 Swirl Inventory Sync {dry_run_badge}</h2>
      <p style="color:#6b7280;font-size:13px">{result['started_at']} UTC · {result['duration_seconds']:.1f}s</p>

      <table style="width:100%;border-collapse:collapse;margin:16px 0">
        <tr style="background:#f0fdf4">
          <td style="padding:12px;text-align:center">
            <div style="font-size:28px;font-weight:bold;color:#16a34a">{s['updated']}</div>
            <div style="font-size:12px;color:#6b7280">Updated</div>
          </td>
          <td style="padding:12px;text-align:center">
            <div style="font-size:28px;font-weight:bold;color:#d97706">{s['skipped_no_sku_match']}</div>
            <div style="font-size:12px;color:#6b7280">Unmatched SKUs</div>
          </td>
          <td style="padding:12px;text-align:center">
            <div style="font-size:28px;font-weight:bold;color:#6b7280">{s['skipped_zero_stock']}</div>
            <div style="font-size:12px;color:#6b7280">Out of Stock</div>
          </td>
          <td style="padding:12px;text-align:center">
            <div style="font-size:28px;font-weight:bold;color:#dc2626">{s['errors']}</div>
            <div style="font-size:12px;color:#6b7280">Errors</div>
          </td>
        </tr>
      </table>

      {unmatched_rows}
      {error_rows}

      <p style="font-size:11px;color:#9ca3af;margin-top:24px">
        Swirl Inventory Sync · Agentway · Next sync in ~12 hours
      </p>
    </div>
    """


async def send_sync_summary(result: dict) -> None:
    if not settings.resend_api_key or not settings.alert_email_to:
        logger.info("Resend not configured — skipping email summary")
        return

    errors = result["summary"]["errors"]
    unmatched = result["summary"]["skipped_no_sku_match"]
    subject = (
        f"✅ Swirl Sync: {result['summary']['updated']} updated"
        if errors == 0
        else f"⚠️ Swirl Sync: {errors} errors, {result['summary']['updated']} updated"
    )
    if unmatched > 0:
        subject += f" · {unmatched} unmatched SKUs"

    payload = {
        "from": settings.alert_email_from,
        "to": [settings.alert_email_to],
        "subject": subject,
        "html": _build_email_html(result),
    }

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {settings.resend_api_key}"},
            json=payload,
        )
        if resp.status_code in (200, 201):
            logger.info("Sync summary email sent")
        else:
            logger.error(f"Resend failed: {resp.status_code} {resp.text}")
