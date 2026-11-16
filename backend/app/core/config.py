from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HMS_", env_file=".env", extra="ignore")

    database_url: str | None = None
    system_owner_username: str | None = None
    environment: str = "development"
    cors_origins: list[str] = ["http://localhost:5173"]
    session_cookie_name: str = "tether_session"
    csrf_cookie_name: str = "tether_csrf"
    session_ttl_hours: int = Field(default=8, gt=0, le=24)
    login_lockout_attempts: int = Field(default=5, ge=3)
    login_lockout_minutes: int = Field(default=15, gt=0)


def get_settings() -> Settings:
    return Settings()
