from __future__ import annotations

from typing import Optional

from .event_bus import EventBus
from .executor import PriorityExecutor
from .session_manager import SessionManager


class Orchestrator:
	def __init__(self) -> None:
		self.events = EventBus()
		self.exec = PriorityExecutor()
		self.sessions = SessionManager()

	def ensure_session(self, session_id: Optional[str]) -> str:
		sid = session_id or "default"
		self.sessions.get_or_create(sid)
		return sid