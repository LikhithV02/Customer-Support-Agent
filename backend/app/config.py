from functools import lru_cache
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parent.parent

# Only ever used when AUTH_MODE=dev. Startup refuses to run in prod with it.
DEV_JWT_SECRET = "dev-insecure-secret-change-me-0123456789"


def _async_db_url(url: str) -> str:
    """Normalise a DB URL to its async driver (asyncpg / aiosqlite)."""
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        return _asyncpg_query("postgresql+asyncpg://" + url[len("postgresql://") :])
    if url.startswith("sqlite:///"):
        return "sqlite+aiosqlite:///" + url[len("sqlite:///") :]
    return url


def _asyncpg_query(url: str) -> str:
    """Translate libpq query params (as in Neon/Supabase URLs) for asyncpg.

    asyncpg takes `ssl=` instead of `sslmode=` and rejects libpq-only options
    such as `channel_binding`.
    """
    parts = urlsplit(url)
    if not parts.query:
        return url
    params = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        if key == "sslmode":
            params.append(("ssl", value))
        elif key not in ("channel_binding", "options"):
            params.append((key, value))
    return urlunsplit(parts._replace(query=urlencode(params)))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # "dev" enables the dev-token endpoint, in-process Redis fallback and
    # permissive defaults. "prod" requires real secrets, Redis and Postgres.
    env: str = "dev"

    # LLM provider: "anthropic", "openai" or "fake" (scripted, for load tests)
    llm_provider: str = "anthropic"
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-6"
    openai_model: str = "gpt-4o"
    # Optional secondary provider used when the primary errors (e.g. "openai").
    llm_fallback_provider: str = ""
    llm_timeout_s: float = 60.0
    llm_max_retries: int = 2
    # Fake provider knobs (LLM_PROVIDER=fake)
    fake_llm_latency_ms: int = 1500
    fake_llm_error_rate: float = 0.0

    # Storage. Plain postgresql:// / sqlite:/// URLs are upgraded to async drivers.
    database_url: str = f"sqlite:///{BACKEND_ROOT / 'var' / 'app.db'}"
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_timeout_s: float = 10.0
    # Dev convenience: create tables + load fixture data on startup. In
    # compose/k8s, migrations run as a separate job instead.
    seed_on_startup: bool = False

    # Redis. Empty in dev/tests → in-process fakeredis (single process only).
    redis_url: str = ""

    # Auth (see docs/PRODUCTION.md). Tokens are issued by the host site.
    # "dev" (local token picker) | "jwt" (host site issues tokens) |
    # "demo" (public sandbox: anonymous visitors get a throwaway customer).
    auth_mode: str = "dev"
    jwt_secret: str = ""
    jwt_jwks_url: str = ""
    jwt_issuer: str = ""
    jwt_audience: str = ""
    dev_token_ttl_s: int = 8 * 3600

    # Public demo (AUTH_MODE=demo, see docs/DEPLOY.md)
    demo_session_rate_limit: str = "5/hour"  # new sandboxes per client IP
    demo_token_ttl_s: int = 2 * 3600
    demo_data_ttl_hours: int = 24  # sandbox customers are purged after this
    # Daily token cap across *all* visitors (0 = no cap). Once reached, turns
    # run on the scripted model instead of the real LLM.
    demo_global_daily_token_budget: int = 0
    # Optional Cloudflare Turnstile bot check on sandbox creation.
    turnstile_secret: str = ""

    # HTTP
    cors_origins: str = ""  # comma-separated allowlist
    max_request_bytes: int = 16_384
    # How many proxies in front of us append to X-Forwarded-For (Cloud Run: 1).
    # Used for per-IP limits; 0 = use the socket peer address.
    trusted_proxy_hops: int = 0

    # Refund policy knobs (kept here so policy engine and docs share one source)
    return_window_days: int = 30
    escalation_threshold: float = 500.0

    # Guardrails (see docs/HARDENING.md)
    max_message_chars: int = 2000
    max_conversation_turns: int = 30
    max_conversation_tokens: int = 60000
    customer_daily_token_budget: int = 300_000
    agent_recursion_limit: int = 12
    max_output_tokens: int = 1024
    chat_rate_limit: str = "10/minute"
    # Back-pressure: cap on in-flight agent turns across all pods.
    max_concurrent_turns: int = 200
    turn_timeout_s: float = 120.0

    # Data retention (days) for the retention job.
    retention_days: int = 90

    # Observability
    log_level: str = "INFO"
    log_json: bool = True
    sentry_dsn: str = ""

    @model_validator(mode="after")
    def _check_prod(self) -> "Settings":
        if self.env == "prod":
            problems = []
            if self.auth_mode not in ("jwt", "demo"):
                problems.append("AUTH_MODE must be 'jwt' or 'demo'")
            if not (self.jwt_jwks_url or self.jwt_secret):
                problems.append("JWT_SECRET or JWT_JWKS_URL is required")
            if self.auth_mode == "demo" and (self.jwt_jwks_url or len(self.jwt_secret) < 32):
                # The demo mints its own tokens, so it needs a strong HS256 secret.
                problems.append("AUTH_MODE=demo needs JWT_SECRET (>= 32 chars) and no JWKS")
            if self.jwt_secret == DEV_JWT_SECRET:
                problems.append("JWT_SECRET must not be the dev secret")
            if not self.redis_url:
                problems.append("REDIS_URL is required")
            if self.async_database_url.startswith("sqlite"):
                problems.append("DATABASE_URL must point at Postgres")
            if problems:
                raise ValueError("invalid production config: " + "; ".join(problems))
        return self

    @property
    def async_database_url(self) -> str:
        return _async_db_url(self.database_url)

    @property
    def effective_jwt_secret(self) -> str:
        if self.jwt_secret:
            return self.jwt_secret
        # Local dev/demo only; prod startup requires a real JWT_SECRET.
        return DEV_JWT_SECRET if self.auth_mode in ("dev", "demo") else ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_demo(self) -> bool:
        return self.auth_mode == "demo"

    @property
    def has_llm_key(self) -> bool:
        if self.llm_provider == "anthropic":
            return bool(self.anthropic_api_key)
        if self.llm_provider == "openai":
            return bool(self.openai_api_key)
        return self.llm_provider == "fake"


@lru_cache
def get_settings() -> Settings:
    return Settings()
