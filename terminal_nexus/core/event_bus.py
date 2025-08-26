from __future__ import annotations

from collections import defaultdict
from typing import Callable, Dict, List, Any


EventHandler = Callable[[str, Dict[str, Any]], None]


class EventBus:
	def __init__(self) -> None:
		self._subscribers: Dict[str, List[EventHandler]] = defaultdict(list)

	def subscribe(self, event_type: str, handler: EventHandler) -> None:
		self._subscribers[event_type].append(handler)

	def publish(self, event_type: str, payload: Dict[str, Any]) -> None:
		for handler in list(self._subscribers.get(event_type, [])):
			handler(event_type, payload)