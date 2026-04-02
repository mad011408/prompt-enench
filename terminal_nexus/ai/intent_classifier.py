from __future__ import annotations


def classify_intent(text: str) -> str:
	lower = text.lower()
	if lower.startswith(("run ", "exec ", "execute ", "bash ", "sh ")):
		return "execute_command"
	if lower.startswith(("search ", "google ", "web ")):
		return "web_search"
	if any(k in lower for k in ["code", "function", "class", "bug", "fix"]):
		return "code_assist"
	return "chat"