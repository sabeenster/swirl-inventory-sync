# Swirl Inventory Sync Agent
**Toast → Shopify inventory sync for Swirl on Castro**
Runs twice daily (6am + 6pm PT). Matches on SKU, applies a configurable buffer, updates Shopify inventory levels, and emails a summary via Resend.

---

## Files
```
app/
  main.py          # FastAPI app + APScheduler (6am/6pm PT cron)
  config.py        # Pydantic settings — all config via env vars
  sync.py          # Core sync logic (match SKUs, apply buffer, push)
  toast_client.py  # Toast OAuth + menu items + stock API
  shopify_client.py# Shopify Admin API — variants + inventory levels
  email_alerts.py  # Resend email summary
Procfile           # Railway entrypoint
requirements.txt
.env.example
```

---

## Deploy to Railway

1. Push this repo to GitHub
2. New Railway project → Deploy from GitHub repo
3. Add environment variables (copy from `.env.example`)
4. Railway auto-detects Procfile and deploys

---

## Environment Variables

| Variable | Where to get it |
|---|---|
| `TOAST_CLIENT_ID` | Toast Web → Integrations → Toast API access → Manage credentials |
| `TOAST_CLIENT_SECRET` | Same as above |
| `TOAST_RESTAURANT_GUID` | Same page — your restaurant GUID |
| `SHOPIFY_STORE_DOMAIN` | Your myshopify.com domain |
| `SHOPIFY_ACCESS_TOKEN` | Shopify Admin → Apps → Develop apps → Admin API |
| `SHOPIFY_LOCATION_ID` | Shopify Admin → Settings → Locations → click location → ID in URL |
| `RESEND_API_KEY` | Resend dashboard (same key as wine enrichment agent) |
| `INVENTORY_BUFFER_PCT` | Default `0.10` (holds back 10% to avoid oversells) |
| `DRY_RUN` | Set `true` to test without writing to Shopify |

---

## Getting your Shopify Location ID

Go to: Shopify Admin → Settings → Locations → click your store location
The ID is the number at the end of the URL:
`/admin/settings/locations/12345678` → Location ID is `12345678`

---

## Manual Trigger

POST to `/sync/trigger` to run a sync immediately (useful after a big receiving day):
```bash
curl -X POST https://your-railway-url.up.railway.app/sync/trigger
```

---

## SKU Matching

The agent matches Toast items to Shopify variants **by SKU**. For this to work:
- Every wine you want to sync must have the **same SKU string** in both Toast and Shopify
- Items in Toast with no SKU are skipped (logged)
- Items in Toast with a SKU that has no Shopify match are flagged in the email summary as "Unmatched SKUs"

**One-time setup:** Export your Toast menu and Shopify products to CSV, compare SKUs, fix mismatches. The email summary will surface any remaining gaps after the first real run.

---

## Inventory Buffer

`INVENTORY_BUFFER_PCT=0.10` means: if Toast shows 10 bottles, Shopify will show 9.
This prevents oversells when there's a lag between a sale happening in-store and the next sync.

Set to `0.0` to sync exact quantities.

---

## Adding Toast credentials (once support resolves)

1. Toast Web → Integrations → Toast API access → Manage credentials → Create new
2. Copy Client ID, Client Secret, Restaurant GUID into Railway env vars
3. Trigger a manual sync to verify: `POST /sync/trigger`
