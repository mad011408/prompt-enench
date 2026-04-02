from __future__ import annotations

from functools import wraps
from typing import Callable


def safe_call(fn: Callable):
	@wraps(fn)
	def wrapper(*args, **kwargs):
		try:
			return fn(*args, **kwargs)
		except Exception as ex:  # nontrivial: in production, log with context
			return f"[error] {ex}"
	return wrapper