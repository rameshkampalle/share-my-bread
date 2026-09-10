from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["development", "demo", "production"] = "development"
    app_name: str = "Share My Bread"
    app_version: str = "0.1.0"
    log_level: str = "INFO"
    database_url: str | None = None
    supabase_url: str | None = None
    supabase_anon_key: str | None = None
    supabase_publishable_key: str | None = None
    supabase_service_role_key: str | None = None
    cors_allowed_origins: str = ""
    n8n_agent_webhook_url: str | None = None
    n8n_event_webhook_url: str | None = None
    n8n_webhook_secret: str | None = Field(default=None, repr=False)
    mem0_api_key: str | None = Field(default=None, repr=False)
    mem0_enabled: bool = False
    ai_assistant_enabled: bool = True
    semantic_search_enabled: bool = True
    dev_fulfilment_mode: bool = True
    retailer_integration_mode: Literal["mock", "external"] = "mock"
    payment_mode: Literal["cash"] = "cash"

    @property
    def allowed_origins(self) -> list[str]:
        return [value.strip() for value in self.cors_allowed_origins.split(",") if value.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
