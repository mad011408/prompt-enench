from __future__ import annotations

import json
from typing import Dict, Any, List, Optional
import requests

from utils.config_manager import NexusConfig


class GeminiEngine:
	def __init__(self, config: NexusConfig):
		self._config = config

	def generate(self, system_prompt: str, messages: List[Dict[str, str]], temperature: float = 0.3) -> str:
		payload = self._build_payload(system_prompt, messages, temperature)
		headers = {
			"Content-Type": "application/json",
		}
		params = {"key": self._config.gemini.api_key}
		response = requests.post(
			self._config.gemini.base_url,
			headers=headers,
			params=params,
			data=json.dumps(payload),
			timeout=self._config.gemini.timeout_seconds,
		)
		response.raise_for_status()
		data = response.json()
		return self._extract_text(data)

	def _build_payload(self, system_prompt: str, messages: List[Dict[str, str]], temperature: float) -> Dict[str, Any]:
		contents = []
		if system_prompt:
			contents.append({"role": "user", "parts": [{"text": system_prompt}]})
		for msg in messages:
			contents.append({
				"role": msg.get("role", "user"),
				"parts": [{"text": msg.get("content", "")}],
			})
		return {
			"contents": contents,
			"generationConfig": {
				"temperature": temperature,
				"maxOutputTokens": self._config.gemini.max_tokens,
			},
		}

	@staticmethod
	def _extract_text(resp: Dict[str, Any]) -> str:
		candidates = resp.get("candidates", [])
		if not candidates:
			return ""
		content = candidates[0].get("content", {})
		parts = content.get("parts", [])
		texts = [p.get("text", "") for p in parts]
		return "".join(texts)