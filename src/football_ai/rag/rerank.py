"""bge-reranker-v2-m3 cross-encoder wrapper.

The retrievers are bi-encoders: every chunk's vector was computed before the
question existed, so similarity is the best they can offer. A cross-encoder
reads the question and the passage *together* and answers a different, harder
question - does this passage address this query - which is why it can fix
rankings a vector search cannot.

It pays for that with cost: one forward pass per (query, passage) pair, on
CPU, seconds rather than milliseconds. So it runs last, over the handful of
candidates fusion already shortlisted, never over the corpus.

Same posture as embeddings.Embedder: tests inject a fake model (anything with
a `.predict()` method), and the real
`sentence_transformers.CrossEncoder("BAAI/bge-reranker-v2-m3")` is imported
lazily on first use, so importing this module never triggers a download.
"""

from __future__ import annotations

from typing import Any

import numpy as np

RERANK_MODEL = "BAAI/bge-reranker-v2-m3"


class Reranker:
    def __init__(self, model: Any | None = None, model_name: str = RERANK_MODEL) -> None:
        self._model = model
        self._model_name = model_name

    def _load_model(self) -> Any:
        if self._model is None:
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(self._model_name)
        return self._model

    def score(self, query: str, passages: list[str]) -> np.ndarray:
        """Relevance of each passage to the query, squashed into [0, 1].

        bge-reranker emits an unbounded logit. A sigmoid is applied here so
        that the number stored on a passage and compared against
        `rerank_abstain_threshold` is readable: 0.9 means "clearly relevant"
        rather than "4.2, which is apparently high".
        """
        if not passages:
            # before _load_model: an empty candidate list must not pay for a
            # 600 MB download
            return np.zeros(0, dtype=np.float32)
        model = self._load_model()
        logits = np.asarray(
            model.predict([(query, passage) for passage in passages]),
            dtype=np.float32,
        )
        if logits.shape[0] != len(passages):
            msg = f"reranker returned {logits.shape[0]} scores for {len(passages)} passages"
            raise ValueError(msg)
        return (1.0 / (1.0 + np.exp(-logits))).astype(np.float32)
