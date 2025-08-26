from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Iterable, List, Any


class ParallelExecutor:
	def __init__(self, max_workers: int = 8):
		self._pool = ThreadPoolExecutor(max_workers=max_workers)

	def map(self, fn: Callable[[Any], Any], items: Iterable[Any]) -> List[Any]:
		futs = [self._pool.submit(fn, it) for it in items]
		return [f.result() for f in as_completed(futs)]