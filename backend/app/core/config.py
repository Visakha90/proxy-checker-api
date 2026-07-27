from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://proxydb:proxydb_secret_2024@db:5432/proxy_checker"

    # Redis
    redis_url: str = "redis://redis:6379/0"

    # Auth
    secret_key: str = "change-me-in-production-use-openssl-rand-hex-32"
    admin_username: str = "admin"
    admin_password: str = "admin123"
    access_token_expire_minutes: int = 1440
    algorithm: str = "HS256"

    # Name.com DNS
    namecom_username: str = ""
    namecom_api_token: str = ""
    namecom_api_url: str = "https://api.name.com/v4"

    # Telegram Bot
    telegram_bot_token: str = ""
    telegram_admin_chat_id: str = ""

    # Stripe
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_pro: str = "price_pro_monthly"
    stripe_price_enterprise: str = "price_enterprise_monthly"

    # CAPTCHA
    captcha_api_key: str = ""
    captcha_provider: str = "2captcha"

    # Scraper
    scrape_interval_seconds: int = 10
    check_interval_seconds: int = 30
    check_concurrency: int = 500
    check_timeout: int = 10
    max_failures_before_delete: int = 3
    max_proxy_age_hours: int = 24
    retry_count: int = 2

    class Config:
        env_file = ".env"
        extra = "allow"


@lru_cache
def get_settings() -> Settings:
    return Settings()
