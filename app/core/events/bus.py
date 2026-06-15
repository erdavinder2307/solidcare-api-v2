"""
In-process event bus for domain events.

Usage:
    event_bus.publish(AppointmentBooked(appointment_id=..., patient_id=...))

Handlers are registered via @event_bus.subscribe(EventClass).
In Phase 13 (SaaS), this can be swapped for Azure Service Bus.
"""

import asyncio
import logging
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class DomainEvent:
    """Base class for all domain events."""
    pass


class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[type[DomainEvent], list[Callable]] = defaultdict(list)

    def subscribe(self, event_type: type[DomainEvent]):
        def decorator(handler: Callable):
            self._handlers[event_type].append(handler)
            return handler
        return decorator

    async def publish(self, event: DomainEvent) -> None:
        event_type = type(event)
        handlers = self._handlers.get(event_type, [])
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            except Exception:
                logger.exception("Event handler %s failed for %s", handler.__name__, event_type.__name__)


event_bus = EventBus()
