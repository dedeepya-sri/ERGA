"""
Rubric-criterion <-> evidence retrieval (Sections 9-10).

Two engines share one interface (`Embedder`) so the rest of the pipeline
never knows or cares which is active:

  * TfidfEmbedder  — scikit-learn TF-IDF + cosine similarity. Deterministic,
    fully explainable (you can point at exactly which shared terms drove a
    similarity score), and needs no model download. This is the active
    default (see config/model_config.yaml).

  * SBERTEmbedder — sentence-transformers dense embeddings. This is the
    "true" Sentence-BERT retrieval the spec calls for in Section 9, fully
    implemented below. It is lazy-imported and will raise a clear,
    actionable RuntimeError if `sentence-transformers` isn't installed or
    the model can't be downloaded — it will NOT silently fall back and
    pretend to be TF-IDF. Activate it by installing the optional deps
    (requirements.txt) and setting `embedding_model.engine: sbert` in
    model_config.yaml, in an environment that can reach the model hub.

Both engines expose the same `retrieve()` method used by the grading
pipeline, returning `RetrievedEvidence` objects that are always verbatim
substrings of the answer (never generated text).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from config.settings import Config
from services.segmentation import Segment
from services.text_utils import stemmed_tokenizer


@dataclass
class RetrievedEvidence:
    text: str
    similarity: float
    segment_index: int
    line: int


class Embedder(ABC):
    name: str

    @abstractmethod
    def retrieve(
        self,
        query_text: str,
        segments: list[Segment],
        top_k: int,
        min_similarity: float,
    ) -> list[RetrievedEvidence]:
        """Return up to `top_k` segments most similar to `query_text`."""


class TfidfEmbedder(Embedder):
    """
    Fits a fresh TF-IDF vocabulary per submission (over the criterion query
    plus that submission's own segments), so it needs no external corpus and
    behaves identically for any subject. Limitation: this captures lexical
    overlap, not deep paraphrase — a correct answer using very different
    wording from the criterion may score lower than it should. That's the
    principal reason the SBERT path exists as an upgrade (see module
    docstring).
    """

    name = "tfidf-cosine"

    def __init__(self, config: Config):
        self._cfg = config.embedding.tfidf

    def retrieve(
        self,
        query_text: str,
        segments: list[Segment],
        top_k: int,
        min_similarity: float,
    ) -> list[RetrievedEvidence]:
        if not segments:
            return []

        corpus = [query_text] + [s.text for s in segments]
        vectorizer = TfidfVectorizer(
            max_features=self._cfg["max_features"],
            ngram_range=tuple(self._cfg["ngram_range"]),
            min_df=self._cfg["min_df"],
            tokenizer=stemmed_tokenizer,
            token_pattern=None,  # required by sklearn when a custom tokenizer is supplied
            lowercase=False,  # already lowercased inside stemmed_tokenizer
        )
        try:
            matrix = vectorizer.fit_transform(corpus)
        except ValueError:
            # Happens if, after stop-word removal, the corpus is empty
            # (e.g. an answer of only stop-words). No evidence, not an error.
            return []

        query_vec = matrix[0]
        segment_vecs = matrix[1:]
        sims = cosine_similarity(query_vec, segment_vecs)[0]

        ranked = sorted(
            zip(segments, sims), key=lambda pair: pair[1], reverse=True
        )
        results = [
            RetrievedEvidence(
                text=seg.text,
                similarity=round(float(sim), 4),
                segment_index=seg.index,
                line=seg.line,
            )
            for seg, sim in ranked
            if sim >= min_similarity
        ]
        return results[:top_k]


class SBERTEmbedder(Embedder):
    """Sentence-BERT dense retrieval — see module docstring for activation."""

    name = "sentence-transformers"

    def __init__(self, config: Config):
        try:
            from sentence_transformers import SentenceTransformer  # noqa: PLC0415
        except ImportError as exc:
            raise RuntimeError(
                "embedding_model.engine is set to 'sbert' but the "
                "'sentence-transformers' package isn't installed. Install "
                "the optional dependencies in requirements.txt to use it."
            ) from exc

        model_name = config.embedding.sbert["name"]
        try:
            self._model = SentenceTransformer(model_name)
        except Exception as exc:  # noqa: BLE001 — surfacing the real cause matters here
            raise RuntimeError(
                f"Could not load SBERT model '{model_name}'. This usually "
                "means there is no network route to the model hub to "
                "download the weights. TF-IDF remains available as "
                "embedding_model.engine: tfidf."
            ) from exc

    def retrieve(
        self,
        query_text: str,
        segments: list[Segment],
        top_k: int,
        min_similarity: float,
    ) -> list[RetrievedEvidence]:
        if not segments:
            return []
        texts = [s.text for s in segments]
        query_emb = self._model.encode([query_text], normalize_embeddings=True)
        seg_embs = self._model.encode(texts, normalize_embeddings=True)
        sims = np.dot(seg_embs, query_emb[0])

        ranked = sorted(zip(segments, sims), key=lambda pair: pair[1], reverse=True)
        results = [
            RetrievedEvidence(
                text=seg.text,
                similarity=round(float(sim), 4),
                segment_index=seg.index,
                line=seg.line,
            )
            for seg, sim in ranked
            if sim >= min_similarity
        ]
        return results[:top_k]


def get_embedder(config: Config) -> Embedder:
    if config.embedding.engine == "sbert":
        return SBERTEmbedder(config)
    return TfidfEmbedder(config)
