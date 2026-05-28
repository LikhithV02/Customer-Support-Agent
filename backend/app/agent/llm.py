"""Provider-agnostic chat model factory.

Returns a LangChain chat model for the configured provider. Both models support
`bind_tools`, so the LangGraph agent is identical regardless of provider.
"""

from app.config import get_settings


def get_chat_model():
    settings = get_settings()
    provider = settings.llm_provider.lower()

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
            max_tokens=1024,
        )

    if provider == "openai":
        from langchain_openai import ChatOpenAI

        if not settings.openai_api_key:
            raise RuntimeError("LLM_PROVIDER=openai but OPENAI_API_KEY is not set.")
        return ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            temperature=0,
        )

    raise RuntimeError(
        f"Unknown LLM_PROVIDER '{settings.llm_provider}'. Use 'anthropic' or 'openai'."
    )
