from __future__ import annotations

from typing import List, Dict

from utils.config_manager import NexusConfig
from ai.gemini_engine import GeminiEngine
from .orchestrator import Orchestrator


class Brain:
	def __init__(self, config: NexusConfig):
		self._config = config
		self._llm = GeminiEngine(config)
		self._orch = Orchestrator()

	def chat(self, user_input: str, session_id: str | None = None) -> str:
		sid = self._orch.ensure_session(session_id)
		self._orch.events.publish("user_input", {"session_id": sid, "text": user_input})
		system_prompt = (
			"You are Terminal Nexus, an ultra-advanced enterprise terminal AI agent. "
			"You must be helpful, concise, and safe."
		)
		messages: List[Dict[str, str]] = [
			{"role": "user", "content": user_input},
		]
		reply = self._llm.generate(system_prompt=system_prompt, messages=messages)
		self._orch.events.publish("assistant_output", {"session_id": sid, "text": reply})
		return reply