from __future__ import annotations

from collections import OrderedDict
from typing import Any


class ModelCache:
	def __init__(self, max_items: int = 128):
		self._data: OrderedDict[str, Any] = OrderedDict()
		self._max = max_items

	def get(self, key: str) -> Any | None:
		val = self._data.get(key)
		if val is not None:
			self._data.move_to_end(key)
		return val

	def set(self, key: str, value: Any) -> None:
		self._data[key] = value
		self._data.move_to_end(key)
		while len(self._data) > self._max:
			self._data.popitem(last=False)