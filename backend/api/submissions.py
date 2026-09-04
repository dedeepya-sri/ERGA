"""Submission upload, extraction, grading, and result endpoints (Sections 22-25, 41-42)."""
from __future__ import annotations

import re
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session, joinedload

from config.settings import config
from database.db import get_db
from database.models import CriterionResult, ExtractedAnswer, Question, Submission
from schemas.schemas import (
    CriterionResultOut,
    EvidenceOut,
    ExtractedAnswerOut,
    ExtractedTextUpdate,
    GradingResultOut,
    ReviewOut,
    SubmissionOut,
)
from services.confidence import criterion_review_reasons, submission_review_decision
from services.extraction import ExtractionError, extract_from_image, extract_from_pdf
from services.grading_pipeline import grade_submission
from services.scoring import total_marks

router = APIRouter(prefix="/api/submissions", tags=["submissions"])

ALLOWED_INPUT_TYPES = {"typed", "pdf", "scan", "handwritten"}


def _sanitize_filename(filename: str) -> str:
    """Section 50: 'sanitize filenames'. Strips any path component and unsafe characters."""
    base = Path(filename).name
    base = re.sub(r"[^A-Za-z0-9_.-]", "_", base) or "upload"
    return f"{uuid.uuid4().hex[:8]}_{base}"


@router.post("", response_model=SubmissionOut, status_code=201)
async def create_submission(
    question_id: int = Form(...),
    input_type: str = Form(...),
    student_identifier: str | None = Form(None),
    text: str | None = Form(None),
    file: UploadFile | None = File(None),
    db: Session = Depends(get_db),
) -> Submission:
    if input_type not in ALLOWED_INPUT_TYPES:
        raise HTTPException(422, f"input_type must be one of {sorted(ALLOWED_INPUT_TYPES)}")

    question = db.query(Question).filter(Question.id == question_id).first()
    if question is None:
        raise HTTPException(404, "Question not found")

    file_path: str | None = None

    if input_type == "typed":
        if not text or not text.strip():
            raise HTTPException(422, "Typed submissions require non-empty 'text'.")
    else:
        if file is None:
            raise HTTPException(422, f"input_type='{input_type}' requires a file upload.")
        ext = Path(file.filename or "").suffix.lower()
        if ext not in config.storage.allowed_extensions:
            raise HTTPException(
                415, f"Unsupported file type '{ext}'. Allowed: {config.storage.allowed_extensions}"
            )

        contents = await file.read()
        size_mb = len(contents) / (1024 * 1024)
        if size_mb > config.storage.max_upload_mb:
            raise HTTPException(413, f"File exceeds the {config.storage.max_upload_mb}MB limit.")

        safe_name = _sanitize_filename(file.filename or "upload")
        dest = config.storage.upload_dir / safe_name
        dest.write_bytes(contents)
        file_path = str(dest)

    submission = Submission(
        question_id=question_id,
        student_identifier=student_identifier,
        input_type=input_type,
        file_path=file_path,
    )
    db.add(submission)
    db.flush()

    if input_type == "typed":
        db.add(
            ExtractedAnswer(
                submission_id=submission.id,
                text=text.strip(),
                recognition_confidence=1.0,
                manually_corrected=False,
                engine="typed",
                source_detail={},
            )
        )

    db.commit()
    db.refresh(submission)
    return submission


@router.post("/{submission_id}/extract", response_model=ExtractedAnswerOut)
def extract_submission(submission_id: int, db: Session = Depends(get_db)) -> ExtractedAnswer:
    submission = db.query(Submission).filter(Submission.id == submission_id).first()
    if submission is None:
        raise HTTPException(404, "Submission not found")
    if submission.input_type == "typed":
        raise HTTPException(400, "Typed submissions are already extracted at creation time.")
    if not submission.file_path:
        raise HTTPException(400, "Submission has no uploaded file to extract.")

    path = Path(submission.file_path)
    if not path.exists():
        raise HTTPException(500, "Uploaded file is missing from storage.")

    try:
        if path.suffix.lower() == ".pdf":
            result = extract_from_pdf(path, config)
        else:
            result = extract_from_image(path, config)
    except ExtractionError as exc:
        # Already a clear, actionable, user-safe message (encrypted PDF,
        # corrupted file, Tesseract not installed, ...) — pass it through
        # as-is rather than wrapping it in a generic "Extraction failed:".
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 — anything unanticipated still needs to surface, not hang
        raise HTTPException(
            500, f"Extraction failed unexpectedly ({type(exc).__name__}: {exc or 'no further detail'})."
        ) from exc

    existing = submission.extracted_answer
    source_detail = {
        "lines": [
            {"page": line.page, "bbox": line.bbox, "confidence": line.confidence}
            for line in result.lines
        ],
        "page_count": result.page_count,
    }

    if existing is None:
        existing = ExtractedAnswer(submission_id=submission.id)
        db.add(existing)

    existing.text = result.text
    existing.recognition_confidence = result.recognition_confidence
    existing.manually_corrected = False
    existing.engine = result.engine
    existing.source_detail = source_detail

    db.commit()
    db.refresh(existing)
    return existing


@router.get("/{submission_id}/extracted-text", response_model=ExtractedAnswerOut)
def get_extracted_text(submission_id: int, db: Session = Depends(get_db)) -> ExtractedAnswer:
    submission = db.query(Submission).filter(Submission.id == submission_id).first()
    if submission is None:
        raise HTTPException(404, "Submission not found")
    if submission.extracted_answer is None:
        raise HTTPException(404, "Submission has not been extracted yet.")
    return submission.extracted_answer


@router.put("/{submission_id}/extracted-text", response_model=ExtractedAnswerOut)
def correct_extracted_text(
    submission_id: int, payload: ExtractedTextUpdate, db: Session = Depends(get_db)
) -> ExtractedAnswer:
    """Section 22: faculty can correct OCR/HTR mistakes before grading."""
    submission = db.query(Submission).filter(Submission.id == submission_id).first()
    if submission is None:
        raise HTTPException(404, "Submission not found")
    if submission.extracted_answer is None:
        raise HTTPException(400, "Submission has not been extracted yet.")

    submission.extracted_answer.text = payload.text
    submission.extracted_answer.manually_corrected = True
    submission.extracted_answer.recognition_confidence = 1.0  # a human has now verified this text
    db.commit()
    db.refresh(submission.extracted_answer)
    return submission.extracted_answer


def _load_full_submission(db: Session, submission_id: int) -> Submission:
    submission = (
        db.query(Submission)
        .options(
            joinedload(Submission.extracted_answer),
            joinedload(Submission.question).joinedload(Question.criteria),
            joinedload(Submission.criterion_results).joinedload(CriterionResult.criterion),
            joinedload(Submission.criterion_results).joinedload(CriterionResult.evidence),
            joinedload(Submission.criterion_results).joinedload(CriterionResult.review),
        )
        .filter(Submission.id == submission_id)
        .first()
    )
    if submission is None:
        raise HTTPException(404, "Submission not found")
    return submission


@router.post("/{submission_id}/grade", response_model=GradingResultOut)
def grade(submission_id: int, db: Session = Depends(get_db)) -> GradingResultOut:
    submission = _load_full_submission(db, submission_id)
    if not submission.question.criteria:
        raise HTTPException(422, "This question has no rubric criteria yet.")
    try:
        grade_submission(db, submission, config)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    submission = _load_full_submission(db, submission_id)
    return _build_grading_result(submission)


@router.get("/{submission_id}/result", response_model=GradingResultOut)
def get_result(submission_id: int, db: Session = Depends(get_db)) -> GradingResultOut:
    submission = _load_full_submission(db, submission_id)
    if not submission.criterion_results:
        raise HTTPException(404, "Submission has not been graded yet.")
    return _build_grading_result(submission)


@router.get("/{submission_id}", response_model=SubmissionOut)
def get_submission(submission_id: int, db: Session = Depends(get_db)) -> Submission:
    submission = db.query(Submission).filter(Submission.id == submission_id).first()
    if submission is None:
        raise HTTPException(404, "Submission not found")
    return submission


@router.delete("/{submission_id}", status_code=204)
def delete_submission(submission_id: int, db: Session = Depends(get_db)) -> None:
    """Section 50: 'include deletion functionality' for stored examination data."""
    submission = db.query(Submission).filter(Submission.id == submission_id).first()
    if submission is None:
        raise HTTPException(404, "Submission not found")
    if submission.file_path:
        Path(submission.file_path).unlink(missing_ok=True)
    db.delete(submission)
    db.commit()


def _build_grading_result(submission: Submission) -> GradingResultOut:
    question = submission.question
    criteria_out: list[CriterionResultOut] = []
    grading_confidences: list[float] = []
    per_criterion_reasons: list[list[str]] = []

    for cr in sorted(submission.criterion_results, key=lambda c: c.criterion.order_index):
        grading_confidences.append(cr.grading_confidence)
        reasons = criterion_review_reasons(
            f"C{cr.criterion_id} ({cr.criterion.description[:30]})",
            cr.grading_confidence,
            config.thresholds,
        )
        per_criterion_reasons.append(reasons)
        criteria_out.append(
            CriterionResultOut(
                id=cr.id,
                criterion_id=cr.criterion_id,
                description=cr.criterion.description,
                status=cr.status,
                marks=cr.marks,
                max_marks=cr.max_marks,
                composite_score=cr.composite_score,
                grading_confidence=cr.grading_confidence,
                missing_concepts=cr.missing_concepts,
                evidence=[EvidenceOut.model_validate(e) for e in cr.evidence],
                review=ReviewOut.model_validate(cr.review) if cr.review else None,
                engine_info=cr.engine_info,
            )
        )

    recognition_confidence = (
        submission.extracted_answer.recognition_confidence if submission.extracted_answer else 0.0
    )
    already_verified = bool(
        submission.extracted_answer and submission.extracted_answer.manually_corrected
    )
    force_review = (
        submission.input_type == "handwritten"
        and config.ocr.handwriting_force_review
        and not already_verified
    )
    force_reason = (
        "Handwritten input — routed to faculty review pending verification" if force_review else None
    )

    decision = submission_review_decision(
        recognition_confidence, per_criterion_reasons, config.thresholds, force_review, force_reason
    )

    awarded = total_marks([c.marks for c in criteria_out], config.scoring.round_ndigits)
    final = total_marks(
        [c.review.faculty_marks if c.review else c.marks for c in criteria_out],
        config.scoring.round_ndigits,
    )

    return GradingResultOut(
        submission_id=submission.id,
        question_id=question.id,
        question_text=question.question_text,
        total_marks=question.max_marks,
        awarded_marks=awarded,
        final_marks=final,
        recognition_confidence=recognition_confidence,
        grading_confidence=min(grading_confidences) if grading_confidences else 0.0,
        review_required=decision.review_required,
        review_reasons=decision.reasons,
        criteria=criteria_out,
    )
