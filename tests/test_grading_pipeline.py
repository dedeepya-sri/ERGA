"""
Unit tests for the grading engine's internal components, in isolation from
the API/database. Deliberately uses several different subject domains
(civics, biology, physics) rather than the spec's illustrative ML example —
the engine must be general-purpose, not tuned to one worked example.
"""
from __future__ import annotations

from config.settings import load_config
from services.embeddings import TfidfEmbedder
from services.nli import STATUS_MISSING, STATUS_PARTIAL, STATUS_SUPPORTED, LexicalNLIAssessor
from services.scoring import compute_criterion_marks, total_marks
from services.segmentation import segment_into_sentences

CONFIG = load_config()


# --------------------------------- segmentation ---------------------------------


def test_segmentation_splits_on_sentence_boundaries():
    text = "Photosynthesis converts light energy into chemical energy. It occurs in chloroplasts."
    segments = segment_into_sentences(text)
    assert [s.text for s in segments] == [
        "Photosynthesis converts light energy into chemical energy.",
        "It occurs in chloroplasts.",
    ]


def test_segmentation_respects_abbreviations_and_decimals():
    text = "The reaction rate was 3.5 mol/s, e.g. under standard light conditions. Temperature was held constant."
    segments = segment_into_sentences(text)
    # "3.5" must not be split into "3" / "5 mol/s", and "e.g." must not end the sentence early.
    assert len(segments) == 2
    assert "3.5" in segments[0].text
    assert "e.g." in segments[0].text


def test_segmentation_treats_bullets_as_separate_segments():
    text = "- Increases surface area\n- Improves gas exchange"
    segments = segment_into_sentences(text)
    assert len(segments) == 2
    assert segments[0].text == "Increases surface area"


def test_segmentation_never_returns_empty_for_nonempty_input():
    text = "onewordwithnopunctuationatallreallylong"
    segments = segment_into_sentences(text)
    assert len(segments) == 1


# ----------------------------------- retrieval -----------------------------------


def test_tfidf_retrieval_ranks_relevant_segment_first():
    embedder = TfidfEmbedder(CONFIG)
    segments = segment_into_sentences(
        "Federalism divides power between a national government and state governments. "
        "The capital city hosts an annual film festival. "
        "Regional governments can pass their own local laws under this system."
    )
    results = embedder.retrieve(
        query_text="Defines federalism as a division of power between national and state government",
        segments=segments,
        top_k=3,
        min_similarity=0.0,
    )
    assert results, "expected at least one retrieved segment"
    assert "power" in results[0].text.lower() or "federal" in results[0].text.lower()
    # The irrelevant film-festival sentence should not outrank the on-topic ones.
    top_texts = [r.text for r in results[:2]]
    assert not any("film festival" in t.lower() for t in top_texts)


def test_tfidf_retrieval_respects_min_similarity_floor():
    embedder = TfidfEmbedder(CONFIG)
    segments = segment_into_sentences("The weather today is sunny with a light breeze.")
    results = embedder.retrieve(
        query_text="Explain Newton's second law of motion",
        segments=segments,
        top_k=3,
        min_similarity=0.3,
    )
    assert results == []  # nothing about weather should pass as evidence for Newton's second law


# -------------------------------------- NLI ---------------------------------------


def _assess(criterion_text, evidence_answer_text, reference_concepts=None):
    embedder = TfidfEmbedder(CONFIG)
    nli = LexicalNLIAssessor(CONFIG)
    segments = segment_into_sentences(evidence_answer_text)
    retrieved = embedder.retrieve(criterion_text, segments, top_k=3, min_similarity=0.0)
    return nli.assess(criterion_text, reference_concepts or [], retrieved)


def test_nli_supported_for_strong_lexical_match():
    result = _assess(
        criterion_text="Defines federalism as power divided between national and state governments",
        evidence_answer_text=(
            "Federalism is a system of government in which power is divided "
            "between a national government and individual state governments."
        ),
    )
    assert result.status == STATUS_SUPPORTED
    assert result.confidence >= 0.5


def test_nli_not_supported_when_criterion_is_absent():
    result = _assess(
        criterion_text="Gives a real-world country example of a federal system, such as the United States or Germany",
        evidence_answer_text=(
            "Federalism is a system of government in which power is divided "
            "between a national government and individual state governments."
        ),
    )
    assert result.status == STATUS_MISSING
    assert result.missing_concepts  # should name what's missing, not just say "wrong"


def test_nli_negation_prevents_false_support():
    """
    A near-duplicate sentence that negates the criterion shares almost every
    word with it (high bag-of-words similarity) but means the opposite.
    The negation-aware coverage check must stop this from scoring as
    supported despite the high surface similarity.
    """
    result = _assess(
        criterion_text="States that the reaction requires a catalyst to proceed at room temperature",
        evidence_answer_text="The reaction does not require a catalyst to proceed at room temperature.",
    )
    assert result.status != STATUS_SUPPORTED


def test_nli_partial_credit_for_incomplete_answer():
    result = _assess(
        criterion_text=(
            "Explains two advantages of using renewable energy: lower emissions "
            "and reduced long-term fuel cost"
        ),
        evidence_answer_text="Renewable energy produces lower emissions than fossil fuels.",
    )
    assert result.status in (STATUS_PARTIAL, STATUS_SUPPORTED)
    if result.status == STATUS_PARTIAL:
        assert result.missing_concepts


def test_nli_reference_concepts_widen_key_terms():
    """Reference concepts (Section 21) should count toward coverage even if absent from the description text."""
    result = _assess(
        criterion_text="Describes a key process in cellular respiration",
        evidence_answer_text="Glycolysis breaks down glucose into pyruvate in the cytoplasm.",
        reference_concepts=["glycolysis", "glucose breakdown"],
    )
    assert "glycolysi" in " ".join(result.matched_concepts) or result.coverage > 0


# ------------------------------------ scoring -------------------------------------


def test_scoring_is_deterministic_fixed_fraction():
    marks_supported = compute_criterion_marks(STATUS_SUPPORTED, 0.9, max_marks=4, config=CONFIG)
    marks_partial = compute_criterion_marks(STATUS_PARTIAL, 0.5, max_marks=4, config=CONFIG)
    marks_missing = compute_criterion_marks(STATUS_MISSING, 0.1, max_marks=4, config=CONFIG)

    assert marks_supported == 4.0
    assert marks_partial == 2.0  # fixed_fractions.partially_supported = 0.5 in model_config.yaml
    assert marks_missing == 0.0

    # Re-running with identical inputs must reproduce identical output (Rule 5).
    assert compute_criterion_marks(STATUS_SUPPORTED, 0.9, max_marks=4, config=CONFIG) == marks_supported


def test_total_marks_is_a_plain_sum_no_hidden_adjustment():
    assert total_marks([2.0, 1.5, 0.0, 3.0]) == 6.5
