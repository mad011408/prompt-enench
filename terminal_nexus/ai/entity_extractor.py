from __future__ import annotations

from typing import Dict, List


def extract_entities(text: str) -> Dict[str, List[str]]:
	entities: Dict[str, List[str]] = {"urls": [], "paths": [], "emails": []}
	for token in text.split():
		if token.startswith("http://") or token.startswith("https://"):
			entities["urls"].append(token)
		if token.startswith("/"):
			entities["paths"].append(token)
		if "@" in token and "." in token:
			entities["emails"].append(token)
	return entities