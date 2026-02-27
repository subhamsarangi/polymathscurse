from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    DATABASE_URL: str

    ENV: str
    JWT_SECRET: str
    JWT_ISSUER: str

    ACCESS_TTL_MIN: int = 15
    REFRESH_TTL_DAYS: int = 30

    GOOGLE_CLIENT_ID: str

    COOKIE_DOMAIN: str | None = None
    COOKIE_SECURE: bool = False

    ADMIN_EMAIL: str

    STRIPE_API_KEY: str | None = None
    STRIPE_WEBHOOK_SECRET: str | None = None
    STRIPE_PRICE_CENTS: int = 100
    STRIPE_CURRENCY: str = "USD"
    FRONTEND_URL: str | None = None

    @property
    def is_prod(self) -> bool:
        return self.ENV.lower() == "prod"


settings = Settings()
