"""bge-m3 dense embedding wrapper.

bge-m3 also produces sparse and multi-vector output (useful for day 10's
hybrid search), but this day only persists the dense vector, so only the
dense call is wired here.

Tests inject a fake model (anything with an `.encode()` method); the real
`sentence_transformers.SentenceTransformer("BAAI/bge-m3")` is imported lazily
on first use, so importing this module never requires a model download.
"""

from __future__ import annotations

from typing import Any

import numpy as np

DENSE_DIM = 1024
MODEL_NAME = "BAAI/bge-m3"


class Embedder:
    def __init__(self, model: Any | None = None) -> None:
        self._model = model

    def _load_model(self) -> Any:
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(MODEL_NAME)
        return self._model

    def embed(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, DENSE_DIM), dtype=np.float32)
        model = self._load_model()
        vectors = model.encode(texts, normalize_embeddings=True)
        return np.asarray(vectors, dtype=np.float32)
