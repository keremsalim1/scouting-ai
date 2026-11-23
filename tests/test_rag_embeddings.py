"""bge-m3 embedder wrapper: tested with an injected fake model, no download."""

from __future__ import annotations

import numpy as np

from football_ai.rag.embeddings import Embedder


class _FakeModel:
    def encode(self, texts, normalize_embeddings=True):
        return np.zeros((len(texts), 1024), dtype=np.float32)


def test_embed_returns_expected_shape_and_dtype():
    embedder = Embedder(model=_FakeModel())
    out = embedder.embed(["a", "b"])
    assert out.shape == (2, 1024)
    assert out.dtype == np.float32


def test_embed_handles_empty_input_without_calling_model():
    embedder = Embedder(model=_FakeModel())
    assert embedder.embed([]).shape == (0, 1024)
