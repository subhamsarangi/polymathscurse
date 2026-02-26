from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    DATABASE_URL: str

    ENV: str = "dev"
    JWT_SECRET: str
    JWT_ISSUER: str = "polymath-api"

    ACCESS_TTL_MIN: int = 15
    REFRESH_TTL_DAYS: int = 30

    GOOGLE_CLIENT_ID: str

    COOKIE_DOMAIN: str | None = None
    COOKIE_SECURE: bool = False

    ADMIN_EMAIL: str

    @property
    def is_prod(self) -> bool:
        return self.ENV.lower() == "prod"


settings = Settings()
