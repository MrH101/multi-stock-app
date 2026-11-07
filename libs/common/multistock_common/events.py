"""Event bus on Redis Streams.

Services publish domain events (order.created, order.status_changed, ...) and
consumers read them through a consumer group so each event is processed once
per consuming service, even with several replicas.
"""
import json
import logging
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger("events")


class EventPublisher:
    def __init__(self, redis_url: str, stream: str, source: str,
                 webhook_url: str = "", service_token: str = ""):
        self.stream = stream
        self.source = source
        # Dev-only fallback when Redis isn't running: POST events straight to the consumer.
        self.webhook_url = webhook_url
        self.service_token = service_token
        self._redis = None
        if redis_url:
            import redis

            self._redis = redis.Redis.from_url(redis_url)
        self.published: list[dict] = []  # kept for tests / local debugging

    def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        event = {
            "type": event_type,
            "source": self.source,
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "payload": payload,
        }
        self.published.append(event)
        if self._redis is None:
            if self.webhook_url:
                self._post(event)
            else:
                log.info("event (bus disabled): %s", event_type)
            return
        try:
            self._redis.xadd(self.stream, {"event": json.dumps(event, default=str)}, maxlen=100_000)
        except Exception:  # the business transaction already committed; never fail the request
            log.exception("failed to publish event %s", event_type)

    def _post(self, event: dict) -> None:
        import httpx

        try:
            httpx.post(self.webhook_url, json=event, timeout=3,
                       headers={"X-Service-Token": self.service_token})
        except Exception:
            log.exception("failed to deliver event %s to %s", event["type"], self.webhook_url)
