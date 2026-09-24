"""Load shapes, selected with LOAD_SHAPE=<name>.

User counts scale with LT_SCALE (e.g. LT_SCALE=0.25 on a laptop). Durations
scale with LT_TIME_SCALE (e.g. 0.1 for a quick dry run of a long shape).
"""

from __future__ import annotations

import os

from locust import LoadTestShape

SCALE = float(os.getenv("LT_SCALE", "1"))
TIME_SCALE = float(os.getenv("LT_TIME_SCALE", "1"))


def u(n: float) -> int:
    return max(1, int(n * SCALE))


def t(seconds: float) -> float:
    return seconds * TIME_SCALE


class StagedShape(LoadTestShape):
    """Stages of (end_time_s, users, spawn_rate)."""

    abstract = True
    stages: list[tuple[float, int, float]] = []

    def tick(self):
        run_time = self.get_run_time()
        for end, users, rate in self.stages:
            if run_time < end:
                return users, rate
        return None


class Smoke(StagedShape):
    """50 users for 2 minutes — the CI gate."""

    stages = [(t(120), u(50), 10)]


class Ramp(StagedShape):
    """0 → 2,000 users over 10 minutes, hold 10 minutes: steady-state capacity."""

    stages = [
        (t(150), u(500), 5),
        (t(300), u(1000), 5),
        (t(450), u(1500), 5),
        (t(600), u(2000), 5),
        (t(1200), u(2000), 5),
    ]


class Spike(StagedShape):
    """200 users, spike to 3,000 within 30 s, hold, recover: autoscaling + back-pressure."""

    stages = [
        (t(120), u(200), 20),
        (t(300), u(3000), 100),
        (t(480), u(200), 100),
    ]


class Soak(StagedShape):
    """1,000 users for SOAK_MINUTES (default 60): leaks, pool exhaustion, slow drift."""

    minutes = float(os.getenv("SOAK_MINUTES", "60"))
    stages = [(t(minutes * 60), u(1000), 10)]


class Breakpoint(LoadTestShape):
    """+STEP users every STEP_S seconds until SLOs break (or MAX users).

    Stops itself once the unexpected-failure ratio or p95 time-to-first-event
    crosses the SLO, so the last step reached is the system's capacity.
    """

    step = int(os.getenv("BREAKPOINT_STEP", str(u(250))))
    step_s = float(os.getenv("BREAKPOINT_STEP_S", str(t(120))))
    max_users = int(os.getenv("BREAKPOINT_MAX", str(u(10_000))))

    def tick(self):
        stats = self.runner.stats
        run_time = self.get_run_time()
        if run_time > self.step_s:
            from slo import breaching

            reason = breaching(stats, min_requests=200)
            if reason:
                print(f"[breakpoint] stopping at ~{self.runner.user_count} users: {reason}")
                return None
        users = min(self.max_users, self.step * (int(run_time // self.step_s) + 1))
        return users, max(1, self.step / 10)


SHAPES = {
    "smoke": Smoke,
    "ramp": Ramp,
    "spike": Spike,
    "soak": Soak,
    "breakpoint": Breakpoint,
}
