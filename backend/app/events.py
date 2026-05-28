"""In-process pub/sub for live reasoning events.

The chat endpoint runs the agent and, for each reasoning step, persists it and
publishes it here. The admin dashboard subscribes per conversation and streams
those events over SSE in real time. Single backend worker, so a simple in-memory
broadcaster is sufficient (noted in the README).
"""

from __future__ import annotations

import asyncio
from collections import defaultdict


class Broadcaster:
    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue]] = defaultdict(set)

    def subscribe(self, conversation_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers[conversation_id].add(queue)
        return queue

    def unsubscribe(self, conversation_id: str, queue: asyncio.Queue) -> None:
        subs = self._subscribers.get(conversation_id)
        if subs:
            subs.discard(queue)
            if not subs:
                self._subscribers.pop(conversation_id, None)

    def publish(self, conversation_id: str, event: dict) -> None:
        for queue in list(self._subscribers.get(conversation_id, ())):
            queue.put_nowait(event)


broadcaster = Broadcaster()
