"""
Orchestrates one submission through the full grading pipeline (Section 37):

    normalized text -> segmentation -> retrieval -> NLI -> deterministic
    scoring -> persisted CriterionResult + Evidence rows

This is the one function the API layer calls to (re-)grade a submission.
Re-grading is idempotent: existing CriterionResult/Evidence rows for the
submission are replaced, never appended to, so grading the same extracted
text with the same rubric and config always reproduces the same result
(Section 52 Rule 5).
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from config.settings import Config
from database.models import CriterionResult, Evidence, Submission
from services.embeddings import get_embedder
from services.nli import get_nli
from services.scoring import compute_criterion_marks
from services.segmentation import segment_into_sentences


def grade_submission(db: Session, submission: Submission, config: Config) -> Submission:
    if submission.extracted_answer is None or not submission.extracted_answer.text.strip():
        raise ValueError("Submission has no extracted text to grade. Run extraction first.")

    text = submission.extracted_answer.text
    segments = segment_into_sentences(text, min_chars=config.min_segment_chars)
    embedder = get_embedder(config)
    nli = get_nli(config)

    # Idempotent re-grading: clear any prior result for this submission.
    for cr in list(submission.criterion_results):
        db.delete(cr)
    db.flush()

    criteria = sorted(submission.question.criteria, key=lambda c: c.order_index)
    for criterion in criteria:
        retrieved = embedder.retrieve(
            query_text=criterion.description,
            segments=segments,
            top_k=config.retrieval.top_k,
            min_similarity=config.retrieval.min_similarity,
        )
        assessment = nli.assess(
            criterion_text=criterion.description,
            reference_concepts=criterion.reference_concepts or [],
            evidence=retrieved,
        )
        marks = compute_criterion_marks(
            status=assessment.status,
            composite_score=assessment.composite_score,
            max_marks=criterion.marks,
            config=config,
        )

        cr = CriterionResult(
            submission_id=submission.id,
            criterion_id=criterion.id,
            status=assessment.status,
            marks=marks,
            max_marks=criterion.marks,
            composite_score=assessment.composite_score,
            grading_confidence=assessment.confidence,
            missing_concepts=assessment.missing_concepts,
            engine_info={
                "embedder": embedder.name,
                "nli": nli.name,
                "similarity": assessment.similarity,
                "coverage": assessment.coverage,
                "matched_concepts": assessment.matched_concepts,
            },
        )
        db.add(cr)
        db.flush()  # need cr.id before attaching Evidence rows

        # Evidence text is always a verbatim retrieved segment of the
        # student's own (normalized) answer — never generated.
        for ev in retrieved:
            db.add(
                Evidence(
                    criterion_result_id=cr.id,
                    text=ev.text,
                    similarity=ev.similarity,
                    segment_index=ev.segment_index,
                    page=_page_for_line(submission, ev.line),
                    bbox=_bbox_for_line(submission, ev.line),
                )
            )

    db.commit()
    db.refresh(submission)
    return submission


def _line_detail(submission: Submission, line_index: int) -> dict | None:
    """
    Looks up the page/bbox recorded for `line_index` in the extraction
    step's source_detail (see api/submissions.py, which stores it as
    {"lines": [{"page":.., "bbox":.., "confidence":..}, ...]} in the same
    order the text was joined into segments). Returns None for plain typed
    answers, which have no such detail — never fabricated.
    """
    detail = (submission.extracted_answer.source_detail or {}) if submission.extracted_answer else {}
    lines = detail.get("lines")
    if not lines or line_index >= len(lines):
        return None
    return lines[line_index]


def _page_for_line(submission: Submission, line_index: int) -> int | None:
    d = _line_detail(submission, line_index)
    return d.get("page") if d else None


def _bbox_for_line(submission: Submission, line_index: int) -> dict | None:
    d = _line_detail(submission, line_index)
    return d.get("bbox") if d else None
