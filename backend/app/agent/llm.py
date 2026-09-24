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


def _build(provider: str):
    settings = get_settings()
    provider = provider.lower()

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
            max_retries=settings.llm_max_retries,
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
            max_retries=settings.llm_max_retries,
        )

    if provider == "fake":
        from app.agent.llm_fake import ScriptedFakeChatModel

        return ScriptedFakeChatModel(
            latency_ms=settings.fake_llm_latency_ms,
            error_rate=settings.fake_llm_error_rate,
        )

    raise RuntimeError(
        f"Unknown LLM provider '{provider}'. Use 'anthropic', 'openai' or 'fake'."
    )


@lru_cache
def get_model(provider: str):
    """A cached client for `provider` (also used for the demo's scripted mode)."""
    return _build(provider)


def get_chat_model():
    return get_model(get_settings().llm_provider)


@lru_cache
def get_fallback_model():
    """Secondary provider used when the primary fails, or None."""
    settings = get_settings()
    fallback = settings.llm_fallback_provider
    if not fallback or fallback == settings.llm_provider:
        return None
    return get_model(fallback)


def use_prompt_caching() -> bool:
    """Anthropic prompt caching on the system prompt (and, by prefix, the tools).

    Disabled when a real fallback provider is configured, because the same
    message list is replayed to the fallback and other providers reject
    Anthropic's `cache_control` content-block field. The scripted `fake`
    fallback ignores it, so caching stays on.
    """
    settings = get_settings()
    return settings.llm_provider == "anthropic" and settings.llm_fallback_provider in ("", "fake")
