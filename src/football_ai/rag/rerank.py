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
        """Relevance of each passage to the query, in [0, 1].

        The contract is the range, because `rerank_abstain_threshold` has to
        be a readable number: 0.9 means "clearly relevant" rather than "4.2,
        which is apparently high".

        Getting there needs one check rather than an unconditional sigmoid.
        sentence-transformers applies bge-reranker's own sigmoid inside
        `predict()`, so its output is usually already a probability - and
        squashing a second time maps [0, 1] onto [0.5, 0.731], which is not a
        cosmetic error: against the real corpus it turned every irrelevant
        passage into exactly 0.500 and a 0.97 match into 0.726, leaving no gap
        for an abstention threshold to sit in. Raw logits are still handled,
        because whether that activation is applied depends on the model's
        config and the library version, and this wrapper should not break when
        either changes.
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
        if logits.size and (logits.min() < 0.0 or logits.max() > 1.0):
            return (1.0 / (1.0 + np.exp(-logits))).astype(np.float32)
        return logits.astype(np.float32)
