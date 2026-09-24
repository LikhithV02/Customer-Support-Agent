"""Pass/fail SLOs for a load test run (applied when Locust quits).

Thresholds are env-configurable:
  SLO_MAX_FAIL_RATIO     unexpected failures / all requests      (default 0.005)
  SLO_TTFE_P95_MS        p95 time to first SSE event             (default 1500)
  SLO_TURN_P95_MS        p95 full agent turn                     (default 15000)
  SLO_MAX_AGENT_ERRORS   agent_error turns / all turns            (default 0.02)

Expected rejections (409 races, 429 abuse bursts, 503 back-pressure) are
recorded as successes under their own names, so they don't count as failures.
Correctness probes (chat:wrong_decision, race:*, abuse:*) fail the run on any
failure at all.
"""

from __future__ import annotations

import logging
import os

from locust import events

MAX_FAIL_RATIO = float(os.getenv("SLO_MAX_FAIL_RATIO", "0.005"))
TTFE_P95_MS = float(os.getenv("SLO_TTFE_P95_MS", "1500"))
TURN_P95_MS = float(os.getenv("SLO_TURN_P95_MS", "15000"))
MAX_AGENT_ERRORS = float(os.getenv("SLO_MAX_AGENT_ERRORS", "0.02"))

ZERO_TOLERANCE_PREFIXES = ("chat:wrong_decision", "race:", "abuse:")

log = logging.getLogger("slo")


def _entry(stats, name):
    return stats.entries.get((name, "SSE"))


def breaching(stats, min_requests: int = 0) -> str | None:
    """Return a reason string if any SLO is breached, else None."""
    total = stats.total
    if total.num_requests < min_requests:
        return None
    if total.num_requests and total.fail_ratio > MAX_FAIL_RATIO:
        return f"failure ratio {total.fail_ratio:.4f} > {MAX_FAIL_RATIO}"
    ttfe = _entry(stats, "chat:ttfe")
    if ttfe and ttfe.num_requests and ttfe.get_response_time_percentile(0.95) > TTFE_P95_MS:
        return f"p95 ttfe {ttfe.get_response_time_percentile(0.95):.0f}ms > {TTFE_P95_MS:.0f}ms"
    turn = _entry(stats, "chat:full_turn")
    if turn and turn.num_requests and turn.get_response_time_percentile(0.95) > TURN_P95_MS:
        return f"p95 turn {turn.get_response_time_percentile(0.95):.0f}ms > {TURN_P95_MS:.0f}ms"
    return None


def evaluate(stats) -> list[str]:
    problems = []
    reason = breaching(stats)
    if reason:
        problems.append(reason)
    for (name, _method), entry in stats.entries.items():
        if name.startswith(ZERO_TOLERANCE_PREFIXES) and entry.num_failures:
            problems.append(f"{name}: {entry.num_failures} correctness failures")
    for err in stats.errors.values():
        if "500" in str(err.error) or "502" in str(err.error) or "504" in str(err.error):
            problems.append(f"server errors: {err.name} {err.error} x{err.occurrences}")
            break
    turns = _entry(stats, "chat:full_turn")
    errors = _entry(stats, "chat:agent_error")
    if turns and errors:
        ratio = errors.num_requests / max(1, turns.num_requests + errors.num_requests)
        if ratio > MAX_AGENT_ERRORS:
            problems.append(f"agent error ratio {ratio:.3f} > {MAX_AGENT_ERRORS}")
    return problems


@events.quitting.add_listener
def _apply_slos(environment, **_kwargs):
    if getattr(environment.parsed_options, "slo_off", False):
        return
    # In distributed mode only the master has the aggregated stats.
    from locust.runners import WorkerRunner

    if isinstance(environment.runner, WorkerRunner):
        return
    problems = evaluate(environment.stats)
    if problems:
        log.error("SLO FAILED:\n  - " + "\n  - ".join(problems))
        environment.process_exit_code = 1
    else:
        log.info("SLO PASSED")
