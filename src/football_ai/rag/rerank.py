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

# What `predict()` returns. Declared rather than inferred from the values:
# sentence-transformers applies bge-reranker's own sigmoid inside predict(),
# so today the output is a probability - but guessing that per call from
# whether the numbers happen to fall in [0, 1] made the score depend on which
# other candidates shared the batch, and non-monotone across the boundary
# (0.99 -> 0.99 but 1.01 -> 0.733). A relevance score has to be a function of
# (query, passage) and nothing else.
VALID_OUTPUT_SCALES: frozenset[str] = frozenset({"probability", "logit"})


class Reranker:
    def __init__(
        self,
        model: Any | None = None,
        model_name: str = RERANK_MODEL,
        output_scale: str = "probability",
    ) -> None:
        if output_scale not in VALID_OUTPUT_SCALES:
            msg = (
                f"unknown output_scale {output_scale!r}; "
                f"expected one of {sorted(VALID_OUTPUT_SCALES)}"
            )
            raise ValueError(msg)
        self._model = model
        self._model_name = model_name
        self._output_scale = output_scale

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

        How it gets there is governed by `output_scale`, declared at
        construction. `probability` (the default, and what
        sentence-transformers gives for bge-reranker today) passes values
        through and *raises* if any falls outside [0, 1]; `logit` applies the
        sigmoid. Squashing an already-squashed probability is not a cosmetic
        error - it maps [0, 1] onto [0.5, 0.731], which against the real
        corpus turned every irrelevant passage into exactly 0.500 and a 0.97
        match into 0.726, leaving no gap for a threshold to sit in. So if a
        library or model-config change starts emitting logits, this raises
        instead of silently rescaling every score under a threshold that was
        calibrated against the old scale.
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
        if self._output_scale == "logit":
            return (1.0 / (1.0 + np.exp(-logits))).astype(np.float32)
        if logits.min() < 0.0 or logits.max() > 1.0:
            msg = (
                f"output_scale is 'probability' but {self._model_name} returned "
                f"values outside [0, 1] (min {logits.min():.4f}, max "
                f"{logits.max():.4f}); it is emitting logits. Construct the "
                "Reranker with output_scale='logit' and recalibrate "
                "rerank_abstain_threshold - the old threshold was measured "
                "against the other scale."
            )
            raise ValueError(msg)
        return logits.astype(np.float32)
