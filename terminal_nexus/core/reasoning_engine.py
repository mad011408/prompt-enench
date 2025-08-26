from __future__ import annotations

from typing import List, Dict

from ai.gemini_engine import GeminiEngine
from utils.error_handling import safe_call


class ReasoningEngine:
	def __init__(self, llm: GeminiEngine):
		self._llm = llm

	@safe_call
	def solve(self, goal: str) -> str:
		steps_prompt = (
			"Break the problem into clear, numbered steps, solve each step, and verify the final result."
		)
		messages: List[Dict[str, str]] = [
			{"role": "user", "content": f"Goal: {goal}\n{steps_prompt}"},
		]
		return self._llm.generate(system_prompt="Multi-step reasoning.", messages=messages)