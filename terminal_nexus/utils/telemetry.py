from __future__ import annotations

import time
from dataclasses import dataclass
from typing import List


@dataclass
class TelemetryEvent:
	name: str
	timestamp: float
	duration_ms: float


class Telemetry:
	def __init__(self) -> None:
		self._events: List[TelemetryEvent] = []

	def record(self, name: str, duration_ms: float) -> None:
		self._events.append(TelemetryEvent(name=name, timestamp=time.time(), duration_ms=duration_ms))

	def all(self) -> List[TelemetryEvent]:
		return list(self._events)