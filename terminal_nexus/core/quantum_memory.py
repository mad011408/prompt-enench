from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

import numpy as np

from ai.embedding_manager import EmbeddingManager


@dataclass
class MemoryRecord:
	text: str
	vector: np.ndarray
	metadata: dict


class QuantumMemory:
	def __init__(self, dim: int = 512):
		self._embedder = EmbeddingManager(dim)
		self._records: List[MemoryRecord] = []

	def add(self, text: str, metadata: dict | None = None) -> None:
		vec = self._embedder.embed(text)
		self._records.append(MemoryRecord(text=text, vector=vec, metadata=metadata or {}))

	def search(self, query: str, k: int = 5) -> List[Tuple[MemoryRecord, float]]:
		if not self._records:
			return []
		mat = np.vstack([r.vector for r in self._records])
		q = self._embedder.embed(query)
		scores = mat @ q
		idxs = np.argsort(-scores)[:k]
		return [(self._records[int(i)], float(scores[int(i)])) for i in idxs]