"""Redis Streams consumer (consumer group => each event handled once by this service)."""
import asyncio
import json
import logging

from starlette.concurrency import run_in_threadpool

from .config import settings
from .handlers import handle_event

log = logging.getLogger("consumer")


async def consume_forever(session_factory) -> None:
    import redis.asyncio as aioredis

    r = aioredis.Redis.from_url(settings.redis_url)
    try:
        await r.xgroup_create(settings.event_stream, settings.consumer_group, id="0", mkstream=True)
    except Exception:
        pass  # group already exists
    log.info("consuming %s as %s", settings.event_stream, settings.consumer_group)
    while True:
        try:
            batches = await r.xreadgroup(settings.consumer_group, settings.consumer_name,
                                         {settings.event_stream: ">"}, count=50, block=5000)
            for _stream, entries in batches or []:
                for entry_id, fields in entries:
                    try:
                        event = json.loads(fields[b"event"])
                        await run_in_threadpool(_handle, session_factory, event)
                    except Exception:
                        log.exception("failed to handle event %s", entry_id)
                    await r.xack(settings.event_stream, settings.consumer_group, entry_id)
        except asyncio.CancelledError:
            break
        except Exception:
            log.exception("consumer error, retrying in 3s")
            await asyncio.sleep(3)


def _handle(session_factory, event: dict) -> None:
    with session_factory() as s:
        handle_event(s, event)
