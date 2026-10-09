"""Opik tracing for agent turns (optional).

When `OPIK_URL_OVERRIDE` (self-hosted) or `OPIK_API_KEY` (Comet-hosted) is set,
every agent turn is sent to Opik as a trace: model calls with token usage and
estimated cost, tool calls, and the graph steps between them. Turns of one
conversation share a thread (`thread_id` = conversation id).

After a turn, outcome flags (decision, sanitizer correction, injection flag,
fallback, error) are logged as 0/1 feedback scores, so dashboards can chart
rates over time and slice cost and latency by outcome (see
`scripts/opik_dashboards.py`).

This is an analytics layer only. The `ReasoningEvent` table + Redis pub/sub
remain the audit ledger and the live admin stream, and token budgets are still
enforced in `agent/runner.py`. Tracing failures are logged and never fail a turn.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from app.agent.prompts import prompt_version
from app.config import get_settings
from app.observability import log_event

logger = logging.getLogger(__name__)

_DECISIONS = ("approved", "denied", "escalated")

_client = None


def quiet_sdk() -> None:
    """Turn off the Opik SDK's own error reporting and product analytics.

    Must run before `opik` is first imported: on import the SDK calls
    `sentry_sdk.init()` with Comet's DSN, which would replace this app's Sentry
    client (`SENTRY_DSN`) and send our errors to Comet. Set the variables
    explicitly to opt back in.
    """
    os.environ.setdefault("OPIK_SENTRY_ENABLE", "false")
    os.environ.setdefault("OPIK_ANALYTICS_ENABLE", "false")


def fix_anthropic_cache_accounting() -> bool:
    """Stop Opik double-counting Anthropic prompt-cache tokens (opik 2.2.95).

    LangChain's `usage_metadata.input_tokens` already *includes* cache reads and
    writes, but Opik maps it onto Anthropic's raw `input_tokens` (which
    excludes them) and then adds `cache_read_input_tokens` on top. Every cache
    hit is billed twice, at full price and at the cache price, and this app
    caches the system prompt and tools on every Anthropic call.

    The patch only applies while upstream still shows the double count, so it
    switches itself off once Opik fixes the mapping. Returns whether it applied.
    """
    from opik.integrations.langchain.provider_usage_extractors.langchain_run_helpers import (
        langchain_usage,
    )

    usage_cls = langchain_usage.LangChainUsage
    if getattr(usage_cls, "_acme_cache_fix", False):
        return True
    probe = usage_cls.from_original_usage_dict(
        {
            "input_tokens": 100,
            "output_tokens": 1,
            "total_tokens": 101,
            "input_token_details": {"cache_read": 40},
        }
    ).map_to_anthropic_usage()
    if probe.get("input_tokens") != 100:
        return False  # fixed upstream

    original = usage_cls.map_to_anthropic_usage

    def map_to_anthropic_usage(self):
        usage = original(self)
        cached = (usage.get("cache_read_input_tokens") or 0) + (
            usage.get("cache_creation_input_tokens") or 0
        )
        usage["input_tokens"] = max(0, usage["input_tokens"] - cached)
        return usage

    usage_cls.map_to_anthropic_usage = map_to_anthropic_usage
    usage_cls._acme_cache_fix = True
    return True


def _get_client():
    """The process-wide Opik client, created on first use (None when disabled)."""
    global _client
    settings = get_settings()
    if _client is None and settings.opik_enabled:
        quiet_sdk()
        import opik

        fix_anthropic_cache_accounting()

        _client = opik.Opik(
            project_name=settings.opik_project_name,
            workspace=settings.opik_workspace or None,
            host=settings.opik_url_override or None,
            api_key=settings.opik_api_key or None,
        )
        # OpikTracer logs through the global client.
        opik.set_global_client(_client)
    return _client


def configure() -> None:
    try:
        if _get_client() is not None:
            log_event(logger, "opik tracing enabled", project=get_settings().opik_project_name)
    except Exception as exc:  # misconfiguration must not stop the app
        log_event(logger, "opik setup failed", level=logging.WARNING, error=str(exc)[:300])


def flush() -> None:
    if _client is not None:
        try:
            _client.flush(timeout=5)
        except Exception as exc:
            log_event(logger, "opik flush failed", level=logging.WARNING, error=str(exc)[:300])


def tracer_for_turn(conversation_id: str, customer_id: str, *, scripted: bool):
    """An `OpikTracer` callback for one turn, or None when tracing is off."""
    settings = get_settings()
    try:
        if _get_client() is None:
            return None
        from opik.integrations.langchain import OpikTracer

        provider = "fake" if scripted else settings.llm_provider
        tags = [f"provider:{provider}", f"prompt:{prompt_version()}"]
        tags.append("scripted" if scripted else "live")
        if settings.is_demo:
            tags.append("demo")
        return OpikTracer(
            project_name=settings.opik_project_name,
            thread_id=conversation_id,
            tags=tags,
            metadata={
                "customer_id": customer_id,
                "env": settings.env,
                "prompt_version": prompt_version(),
            },
            # Many turns run concurrently in one process; don't touch the shared
            # Opik context stack.
            opik_context_read_only_mode=True,
        )
    except Exception as exc:
        log_event(logger, "opik tracer setup failed", level=logging.WARNING, error=str(exc)[:300])
        return None


@dataclass
class TurnOutcome:
    decision: str | None = None
    corrected: bool = False
    injection_flagged: bool = False
    fallback: bool = False
    error: bool = False


def finish_turn(tracer, outcome: TurnOutcome) -> dict | None:
    """Log outcome scores on the turn's trace; return `{trace_id, url?}` for the timeline.

    The URL is left out in the public demo, whose visitors can't open the Opik
    workspace anyway.
    """
    if tracer is None:
        return None
    settings = get_settings()
    try:
        traces = tracer.created_traces()
        if not traces:
            return None
        trace_id = traces[-1].id
        flags = {f"refund_{d}": outcome.decision == d for d in _DECISIONS}
        flags |= {
            "sanitizer_correction": outcome.corrected,
            "injection_flagged": outcome.injection_flagged,
            "fallback_used": outcome.fallback,
            "turn_error": outcome.error,
        }
        _get_client().log_traces_feedback_scores(
            [
                {
                    "id": trace_id,
                    "name": name,
                    "value": float(value),
                    "project_name": settings.opik_project_name,
                }
                for name, value in flags.items()
            ]
        )
        info = {"trace_id": trace_id}
        if not settings.is_demo:
            from opik import url_helpers
            from opik.config import OPIK_URL_CLOUD

            info["url"] = url_helpers.get_project_url_by_trace_id(
                trace_id, settings.opik_url_override or OPIK_URL_CLOUD
            )
        return info
    except Exception as exc:
        log_event(logger, "opik scoring failed", level=logging.WARNING, error=str(exc)[:300])
        return None
