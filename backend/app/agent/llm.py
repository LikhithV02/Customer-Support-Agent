"""Provider-agnostic chat model factory.

Returns a LangChain chat model for the configured provider. Clients are cached
per process so HTTP connections to the provider are pooled and reused across
requests, with explicit timeouts and retries.

`LLM_PROVIDER=fake` returns a scripted tool-calling model with realistic
latency — used by load tests so they exercise our infrastructure without
spending tokens (see `app/agent/llm_fake.py`).
"""

from __future__ import annotations

from functools import lru_cache

from app.config import get_settings

FAKE_MODEL_NAME = "scripted-fake"


def _build(provider: str, max_retries: int | None = None):
    settings = get_settings()
    provider = provider.lower()
    retries = settings.llm_max_retries if max_retries is None else max_retries

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        if not settings.anthropic_api_key:
            raise RuntimeError(
                "LLM_PROVIDER=anthropic but ANTHROPIC_API_KEY is not set."
            )
        return ChatAnthropic(
            model=settings.anthropic_model,
            api_key=settings.anthropic_api_key,
            temperature=0,
            max_tokens=settings.max_output_tokens,
            timeout=settings.llm_timeout_s,
            max_retries=retries,
        )

    if provider == "openai":
        from langchain_openai import ChatOpenAI

        if not settings.openai_api_key:
            raise RuntimeError("LLM_PROVIDER=openai but OPENAI_API_KEY is not set.")
        return ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            temperature=0,
            max_tokens=settings.max_output_tokens,
            timeout=settings.llm_timeout_s,
            max_retries=retries,
        )

    if provider == "omniroute":
        import httpx
        from langchain_openai import ChatOpenAI

        if not (settings.omniroute_api_key and settings.omniroute_base_url):
            raise RuntimeError(
                "LLM_PROVIDER=omniroute needs OMNIROUTE_BASE_URL and OMNIROUTE_API_KEY."
            )
        # No temperature: GPT-5.x reasoning models only accept the default.
        return ChatOpenAI(
            model=settings.omniroute_model,
            base_url=settings.omniroute_base_url,
            api_key=settings.omniroute_api_key,
            max_tokens=settings.max_output_tokens,
            timeout=httpx.Timeout(settings.llm_timeout_s, connect=settings.llm_connect_timeout_s),
            max_retries=retries,
        )

    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        if not settings.gemini_api_key:
            raise RuntimeError("LLM_PROVIDER=gemini but GEMINI_API_KEY is not set.")
        # No temperature: Google recommends the default (1.0) for Gemini 3;
        # lower values can make it loop. Tool-call thought signatures are
        # carried on the AIMessages, so the graph replays them as-is.
        return ChatGoogleGenerativeAI(
            model=settings.gemini_model,
            google_api_key=settings.gemini_api_key,
            max_tokens=settings.max_output_tokens,
            timeout=settings.llm_timeout_s,
            max_retries=retries,
        )

    if provider == "fake":
        from app.agent.llm_fake import ScriptedFakeChatModel

        return ScriptedFakeChatModel(
            latency_ms=settings.fake_llm_latency_ms,
            error_rate=settings.fake_llm_error_rate,
        )

    raise RuntimeError(
        f"Unknown LLM provider '{provider}'. "
        "Use 'anthropic', 'openai', 'gemini', 'omniroute' or 'fake'."
    )


@lru_cache
def get_model(provider: str, max_retries: int | None = None):
    """A cached client for `provider` (also used for the demo's scripted mode)."""
    return _build(provider, max_retries)


def get_chat_model():
    settings = get_settings()
    if get_fallback_model() is not None:
        # With a fallback available, retrying a dead primary only delays it.
        return get_model(settings.llm_provider, min(settings.llm_max_retries, 1))
    return get_model(settings.llm_provider)


@lru_cache
def get_fallback_model():
    """Secondary provider used when the primary fails, or None."""
    settings = get_settings()
    fallback = settings.llm_fallback_provider
    if not fallback or fallback == settings.llm_provider:
        return None
    return get_model(fallback)


def primary_model_name() -> str:
    """Model id the primary provider answers with (prefix-matched against
    `response_metadata`, since providers may append a dated version)."""
    settings = get_settings()
    return {
        "anthropic": settings.anthropic_model,
        "openai": settings.openai_model,
        "gemini": settings.gemini_model,
        # Proxies report the upstream id without their routing prefix
        # (`cx/gpt-5.6-sol-medium` comes back as `gpt-5.6-sol-medium`).
        "omniroute": settings.omniroute_model.rsplit("/", 1)[-1],
        "fake": FAKE_MODEL_NAME,
    }.get(settings.llm_provider, "")


def use_prompt_caching() -> bool:
    """Anthropic prompt caching on the system prompt (and, by prefix, the tools).

    Disabled when a real fallback provider is configured, because the same
    message list is replayed to the fallback and other providers reject
    Anthropic's `cache_control` content-block field. The scripted `fake`
    fallback ignores it, so caching stays on.
    """
    settings = get_settings()
    return settings.llm_provider == "anthropic" and settings.llm_fallback_provider in ("", "fake")
