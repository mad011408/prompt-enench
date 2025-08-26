from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from typing import Callable, Any, List, Tuple


@dataclass(order=True)
class _PrioritizedTask:
	priority: int
	count: int = field(compare=False)
	action: Callable[[], Any] = field(compare=False)


class PriorityExecutor:
	def __init__(self) -> None:
		self._queue: List[_PrioritizedTask] = []
		self._counter = 0

	def submit(self, action: Callable[[], Any], priority: int = 100) -> None:
		heapq.heappush(self._queue, _PrioritizedTask(priority=priority, count=self._counter, action=action))
		self._counter += 1

	def run_all(self) -> None:
		while self._queue:
			task = heapq.heappop(self._queue)
			task.action()