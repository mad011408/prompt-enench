from __future__ import annotations

from typing import List


class PromptBuilder:
	def __init__(self, persona: str = "Terminal Nexus"):
		self._persona = persona

	def build_system(self, capabilities: List[str]) -> str:
		caps = "; ".join(capabilities)
		return f"You are {self._persona}. Capabilities: {caps}. Respond concisely and safely."

	def build_context(self, history: List[str]) -> str:
		return "\n".join(history[-10:])