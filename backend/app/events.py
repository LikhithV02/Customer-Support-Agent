"""Cross-pod pub/sub for live reasoning events (Redis pub/sub).

The chat endpoint runs the agent and, for each reasoning step, persists it and
publishes it here. The admin dashboard subscribes per conversation and streams
those events over SSE in real time. Because the channel lives in Redis, the
admin can be connected to a different pod than the one running the turn.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

from app.redis import get_redis


def _channel(conversation_id: str) -> str:
    return f"conv:{conversation_id}"


class Broadcaster:
    async def publish(self, conversation_id: str, event: dict) -> None:
        await get_redis().publish(_channel(conversation_id), json.dumps(event))

    async def subscribe(self, conversation_id: str) -> AsyncIterator[dict]:
        pubsub = get_redis().pubsub()
        await pubsub.subscribe(_channel(conversation_id))
        try:
            while True:
                msg = await pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=15.0
                )
                if msg is None:
                    continue
                if msg.get("type") == "message":
                    yield json.loads(msg["data"])
        finally:
            await pubsub.unsubscribe(_channel(conversation_id))
            await pubsub.aclose()


broadcaster = Broadcaster()
