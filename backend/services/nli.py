"""
Criterion <-> evidence semantic assessment (Sections 11, 12, 15).

Produces SUPPORTED / PARTIALLY_SUPPORTED / NOT_SUPPORTED for a criterion
given the evidence retrieved for it. Critically, this module does NOT
decide marks (Section 12: "Don't let NLI directly decide marks") — marks
are computed separately and deterministically in services/scoring.py from
the status this module returns.

Two engines share one interface (`NLIAssessor`):

  * LexicalNLIAssessor (active default) — a deterministic keyword-coverage
    + retrieval-similarity + negation-aware classifier. No model download,
    runs anywhere, and every number it produces is traceable to a specific
    rule ("62% of the criterion's key terms appear in evidence; the
    strongest matching sentence had cosine similarity 0.71"). This is not
    a placeholder — it is a legitimate, fully-working, explainable
    baseline in its own right, and arguably a *better* fit for an
    "explainable/reproducible" system than a neural black box.

  * TransformerNLIAssessor — a HuggingFace NLI text-classification
    pipeline (the DeBERTa/RoBERTa-MNLI class of models Section 11 names).
    Fully implemented and lazy-imported; raises a clear error rather than
    silently downgrading if the model can't be loaded. Activate by
    installing the optional dependencies in requirements.txt and setting
    nli_model.engine: transformer, in an environment that can reach the
    model hub. Not exercised in the reference build (no such network
    route there) — see README.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from config.settings import Config, ThresholdsConfig
from services.embeddings import RetrievedEvidence
from services.text_utils import content_words as _content_words
from services.text_utils import stem as _stem
from services.text_utils import tokenize as _tokenize

STATUS_SUPPORTED = "supported"
STATUS_PARTIAL = "partially_supported"
STATUS_MISSING = "not_supported"

# Negation cues that can flip an otherwise-matched term into "not actually
# supported" (e.g. evidence "does not use labelled data" should NOT count
# as covering the term "labelled").
_NEGATION_CUES = {
    "not", "no", "never", "without", "lack", "lacks", "lacking", "cannot",
    "unable", "fails", "fail", "isn't", "aren't", "doesn't", "don't",
    "didn't", "wasn't", "weren't", "n't",
}
_NEGATION_WINDOW = 4  # tokens after a cue treated as within its scope

# Rubric-writing scaffolding ("Explain...", "Define...", "Name at least
# three...") is instructional framing, not content the student's answer
# needs to echo — a student who correctly defines something shouldn't be
# marked as "missing: define" just because their answer doesn't contain
# the literal word "define". Excluded only from the criterion side of key
# terms; these words are left untouched wherever they appear in evidence.
_RUBRIC_INSTRUCTION_WORDS = {
    "explain", "explains", "explained", "explanation",
    "define", "defines", "defined", "definition",
    "describe", "describes", "described", "description",
    "state", "states", "stated",
    "give", "gives", "given",
    "provide", "provides", "provided",
    "name", "names", "named",
    "list", "lists", "listed",
    "identify", "identifies", "identified",
    "mention", "mentions", "mentioned",
    "discuss", "discusses", "discussed",
    "least", "such", "appropriate", "correct", "correctly", "briefly",
}
_RUBRIC_INSTRUCTION_STEMS = {_stem(w) for w in _RUBRIC_INSTRUCTION_WORDS}


def _criterion_key_terms(criterion_text: str, reference_concepts: list[str]) -> list[str]:
    words = set(_content_words(criterion_text)) - _RUBRIC_INSTRUCTION_STEMS
    for concept in reference_concepts:
        words |= set(_content_words(concept)) - _RUBRIC_INSTRUCTION_STEMS
    return sorted(words)


def _negated_token_positions(tokens: list[str]) -> set[int]:
    negated: set[int] = set()
    for i, tok in enumerate(tokens):
        if tok in _NEGATION_CUES or tok.endswith("n't"):
            for j in range(i + 1, min(i + 1 + _NEGATION_WINDOW, len(tokens))):
                negated.add(j)
    return negated


@dataclass
class NLIAssessment:
    status: str
    composite_score: float
    similarity: float
    coverage: float
    confidence: float
    missing_concepts: list[str]
    matched_concepts: list[str]
    engine: str


class NLIAssessor(ABC):
    name: str

    @abstractmethod
    def assess(
        self,
        criterion_text: str,
        reference_concepts: list[str],
        evidence: list[RetrievedEvidence],
    ) -> NLIAssessment:
        """Assess whether `evidence` supports `criterion_text`."""


def _classify(composite: float, th: ThresholdsConfig) -> str:
    if composite >= th.nli_supported_min:
        return STATUS_SUPPORTED
    if composite >= th.nli_partial_min:
        return STATUS_PARTIAL
    return STATUS_MISSING


def _margin_confidence(composite: float, th: ThresholdsConfig) -> float:
    """
    Confidence = 0.5 + 0.5 * (how far the composite score sits from the
    nearest decision boundary, normalized to its band). A score dead on a
    threshold gets ~0.5; a score deep inside a band approaches 1.0. This is
    a documented heuristic, not an empirically calibrated probability — see
    docs/methodology.md for the calibration protocol that would validate it
    against human graders.
    """
    sup, part = th.nli_supported_min, th.nli_partial_min
    if composite >= sup:
        band = max(1.0 - sup, 0.01)
        margin = composite - sup
    elif composite >= part:
        band = max((sup - part) / 2, 0.01)
        margin = min(composite - part, sup - composite)
    else:
        band = max(part, 0.01)
        margin = part - composite
    return round(0.5 + 0.5 * min(1.0, margin / band), 2)


class LexicalNLIAssessor(NLIAssessor):
    name = "lexical-coverage-v1"

    def __init__(self, config: Config):
        self._cfg = config.nli.lexical
        self._th = config.thresholds

    def assess(
        self,
        criterion_text: str,
        reference_concepts: list[str],
        evidence: list[RetrievedEvidence],
    ) -> NLIAssessment:
        key_terms = _criterion_key_terms(criterion_text, reference_concepts)

        evidence_text = " ".join(e.text for e in evidence)
        ev_tokens = _tokenize(evidence_text)
        ev_stems = [_stem(t) for t in ev_tokens]
        negated_idx = _negated_token_positions(ev_tokens)

        stem_positions: dict[str, list[int]] = {}
        for i, stem in enumerate(ev_stems):
            stem_positions.setdefault(stem, []).append(i)

        matched, missing, negated = [], [], []
        for term in key_terms:
            positions = stem_positions.get(term, [])
            if not positions:
                missing.append(term)
                continue
            usable = [p for p in positions if p not in negated_idx]
            if usable:
                matched.append(term)
            else:
                # The term is literally present but only inside a negated
                # span (e.g. criterion term "renewable" found in "...does
                # NOT use renewable energy..."). Bag-of-words similarity
                # can't tell "uses X" from "does not use X" apart — they
                # share almost every word — so a negated match has to pull
                # the *similarity* term down too, not just coverage, or a
                # flatly contradicting sentence could still score as
                # supported on lexical overlap alone.
                negated.append(term)
                missing.append(term)

        coverage = (len(matched) / len(key_terms)) if key_terms else 0.0
        negation_penalty = (len(negated) / len(key_terms)) if key_terms else 0.0
        raw_similarity = max((e.similarity for e in evidence), default=0.0)
        effective_similarity = raw_similarity * (1 - negation_penalty)

        w_sim = self._cfg["similarity_weight"]
        w_cov = self._cfg["coverage_weight"]
        composite = round(w_sim * effective_similarity + w_cov * coverage, 4) if evidence else 0.0

        status = _classify(composite, self._th)
        confidence = _margin_confidence(composite, self._th)

        return NLIAssessment(
            status=status,
            composite_score=composite,
            similarity=round(raw_similarity, 4),
            coverage=round(coverage, 4),
            confidence=confidence,
            missing_concepts=missing[:6],
            matched_concepts=matched[:10],
            engine=self.name,
        )


class TransformerNLIAssessor(NLIAssessor):
    """
    Real transformer NLI via HuggingFace `transformers.pipeline`. Not
    exercised in the reference build (no network route to the model hub —
    see README "Why TF-IDF/lexical instead of SBERT/transformer"), but
    fully implemented so that switching nli_model.engine to "transformer"
    in an environment with model access is a config change, not a code
    change.
    """

    name = "transformer-nli"

    def __init__(self, config: Config):
        try:
            from transformers import pipeline  # noqa: PLC0415
        except ImportError as exc:
            raise RuntimeError(
                "nli_model.engine is set to 'transformer' but the "
                "'transformers' package isn't installed. Install the "
                "optional dependencies in requirements.txt to use it."
            ) from exc

        model_name = config.nli.transformer["name"]
        try:
            self._pipe = pipeline("text-classification", model=model_name, top_k=None)
        except Exception as exc:  # noqa: BLE001 — surfacing the real cause matters here
            raise RuntimeError(
                f"Could not load NLI model '{model_name}' — this usually "
                "means there is no network route to the model hub to "
                "download the weights in this environment. 'lexical' "
                "remains available as nli_model.engine."
            ) from exc
        self._th = config.thresholds

    def assess(
        self,
        criterion_text: str,
        reference_concepts: list[str],
        evidence: list[RetrievedEvidence],
    ) -> NLIAssessment:
        if not evidence:
            return NLIAssessment(
                status=STATUS_MISSING, composite_score=0.0, similarity=0.0,
                coverage=0.0, confidence=0.85, missing_concepts=[],
                matched_concepts=[], engine=self.name,
            )

        premise = " ".join(e.text for e in evidence)
        hypothesis = criterion_text
        # HF's TextClassificationPipeline accepts a {"text", "text_pair"}
        # dict for pairwise-input tasks like NLI.
        raw = self._pipe({"text": premise, "text_pair": hypothesis})
        scored = raw[0] if raw and isinstance(raw[0], list) else raw
        scores = {item["label"].lower(): item["score"] for item in scored}

        entail = scores.get("entailment", 0.0)
        neutral = scores.get("neutral", 0.0)
        composite = round(entail + 0.5 * neutral, 4)

        if entail >= self._th.nli_supported_min:
            status = STATUS_SUPPORTED
        elif composite >= self._th.nli_partial_min:
            status = STATUS_PARTIAL
        else:
            status = STATUS_MISSING

        confidence = round(max(scores.values()), 2) if scores else 0.5
        return NLIAssessment(
            status=status,
            composite_score=composite,
            similarity=max((e.similarity for e in evidence), default=0.0),
            coverage=round(entail, 4),
            confidence=confidence,
            missing_concepts=[],
            matched_concepts=[],
            engine=self.name,
        )


def get_nli(config: Config) -> NLIAssessor:
    if config.nli.engine == "transformer":
        return TransformerNLIAssessor(config)
    return LexicalNLIAssessor(config)
