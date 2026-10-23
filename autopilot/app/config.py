"""Runtime configuration.

Every integration degrades gracefully to a "dry run" mode so the whole
product can be exercised without Twilio / Stripe / Vapi credentials.
"""
from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Autopilot for Small Trades"
    environment: str = "development"

    # --- core -------------------------------------------------------------
    database_url: Optional[str] = None
    secret_key: str = "dev-only-change-me"
    public_base_url: str = "http://localhost:8000"
    demo_mode: bool = True  # returns OTP codes in API responses for demos

    # --- texting ----------------------------------------------------------
    twilio_account_sid: Optional[str] = None
    twilio_auth_token: Optional[str] = None
    twilio_from_number: Optional[str] = None
    # Twilio will sign webhooks with the auth token when configured.
    verify_twilio_signature: bool = True

    # --- voice ------------------------------------------------------------
    vapi_api_key: Optional[str] = None
    vapi_webhook_secret: Optional[str] = None
    bland_api_key: Optional[str] = None

    # --- payments ---------------------------------------------------------
    stripe_secret_key: Optional[str] = None
    stripe_webhook_secret: Optional[str] = None
    stripe_subscription_price_id: Optional[str] = None
    stripe_subscription_price_id_pro: Optional[str] = None
    frontend_url: Optional[str] = None

    # --- scheduler --------------------------------------------------------
    enable_scheduler: bool = False
    scheduler_interval_seconds: int = 300
    cron_secret: Optional[str] = None

    @property
    def sms_dry_run(self) -> bool:
        return not (self.twilio_account_sid and self.twilio_auth_token)

    @property
    def payments_dry_run(self) -> bool:
        return not self.stripe_secret_key

    @property
    def base_url(self) -> str:
        return (self.frontend_url or self.public_base_url).rstrip("/")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
