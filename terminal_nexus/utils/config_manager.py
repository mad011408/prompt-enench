import os
from dataclasses import dataclass
from typing import Any, Dict

import yaml


@dataclass(frozen=True)
class GeminiConfig:
	api_key: str
	model: str
	base_url: str
	max_tokens: int
	timeout_seconds: int


@dataclass(frozen=True)
class NexusConfig:
	gemini: GeminiConfig


class ConfigManager:
	@staticmethod
	def load(path: str) -> NexusConfig:
		with open(path, "r", encoding="utf-8") as f:
			data: Dict[str, Any] = yaml.safe_load(f)

		api_key = os.getenv("GEMINI_API_KEY", data["gemini"]["api_key"])  # env override
		gemini = GeminiConfig(
			api_key=api_key,
			model=data["gemini"]["model"],
			base_url=data["gemini"]["base_url"],
			max_tokens=int(data["gemini"]["max_tokens"]),
			timeout_seconds=int(data["gemini"]["timeout_seconds"]),
		)
		return NexusConfig(gemini=gemini)