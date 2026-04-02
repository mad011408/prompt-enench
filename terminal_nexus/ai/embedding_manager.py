from __future__ import annotations

import hashlib
from typing import List, Tuple

import numpy as np


class EmbeddingManager:
	def __init__(self, dim: int = 512):
		self._dim = dim

	def embed(self, text: str) -> np.ndarray:
		vec = np.zeros(self._dim, dtype=np.float32)
		for token in text.lower().split():
			h = int(hashlib.sha256(token.encode("utf-8")).hexdigest(), 16)
			idx = h % self._dim
			vec[idx] += 1.0
		norm = np.linalg.norm(vec)
		return vec / (norm + 1e-12)

	def batch_embed(self, texts: List[str]) -> np.ndarray:
		return np.vstack([self.embed(t) for t in texts])

	@staticmethod
	def cosine_similarity(vecs: np.ndarray, query: np.ndarray) -> np.ndarray:
		return np.dot(vecs, query)

	def top_k(self, corpus: List[str], query: str, k: int = 5) -> List[Tuple[int, float]]:
		mat = self.batch_embed(corpus)
		q = self.embed(query)
		scores = self.cosine_similarity(mat, q)
		idxs = np.argsort(-scores)[:k]
		return [(int(i), float(scores[i])) for i in idxs]