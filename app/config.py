from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Toast
    toast_client_id: str = ""
    toast_client_secret: str = ""
    toast_restaurant_guid: str = ""
    toast_api_base: str = "https://ws-api.toasttab.com"

    # Shopify
    shopify_store_domain: str = ""        # e.g. swirl-on-castro.myshopify.com
    shopify_access_token: str = ""        # Admin API token
    shopify_location_id: str = ""         # Inventory location ID

    # Resend (email alerts — same as wine enrichment agent)
    resend_api_key: str = ""
    alert_email_to: str = ""
    alert_email_from: str = ""

    # Sync behavior
    inventory_buffer_pct: float = 0.10    # Hold back 10% to avoid oversells
    dry_run: bool = False                  # If True, log but don't write to Shopify

    class Config:
        env_file = ".env"


settings = Settings()
