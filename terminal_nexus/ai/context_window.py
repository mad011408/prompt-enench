from __future__ import annotations

from typing import List, Tuple


class ContextWindow:
	def __init__(self, max_turns: int = 20):
		self._max_turns = max_turns
		self._history: List[Tuple[str, str]] = []

	def add(self, role: str, content: str) -> None:
		self._history.append((role, content))
		self._history = self._history[-self._max_turns :]

	def render(self) -> List[dict]:
		return [{"role": r, "content": c} for r, c in self._history]