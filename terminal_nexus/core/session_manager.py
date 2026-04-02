from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Any


@dataclass
class Session:
	id: str
	state: Dict[str, Any] = field(default_factory=dict)


class SessionManager:
	def __init__(self) -> None:
		self._sessions: Dict[str, Session] = {}

	def get_or_create(self, session_id: str) -> Session:
		if session_id not in self._sessions:
			self._sessions[session_id] = Session(id=session_id)
		return self._sessions[session_id]