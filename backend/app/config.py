from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # LLM provider: "anthropic" or "openai"
    llm_provider: str = "anthropic"
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-6"
    openai_model: str = "gpt-4o"

    # Storage: default to a file under backend/var (mounted as a volume in Docker)
    database_url: str = f"sqlite:///{BACKEND_ROOT / 'var' / 'app.db'}"

    # Refund policy knobs (kept here so policy engine and docs share one source)
    return_window_days: int = 30
    escalation_threshold: float = 500.0

    @property
    def has_llm_key(self) -> bool:
        if self.llm_provider == "anthropic":
            return bool(self.anthropic_api_key)
        if self.llm_provider == "openai":
            return bool(self.openai_api_key)
        return False


@lru_cache
def get_settings() -> Settings:
    return Settings()
