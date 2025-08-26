from __future__ import annotations

import time


class RateLimiter:
	def __init__(self, rate_per_sec: float, burst: float | None = None):
		self._rate = rate_per_sec
		self._capacity = burst if burst is not None else rate_per_sec
		self._tokens = self._capacity
		self._last = time.time()

	def allow(self, cost: float = 1.0) -> bool:
		now = time.time()
		self._tokens = min(self._capacity, self._tokens + (now - self._last) * self._rate)
		self._last = now
		if self._tokens >= cost:
			self._tokens -= cost
			return True
		return False