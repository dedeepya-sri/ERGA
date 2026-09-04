"""Dashboard + aggregate report endpoints (Sections 19-20, 41, 48-49)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session, joinedload

from config.settings import config
from database.db import get_db
from database.models import Assessment, CriterionResult, Question, Submission
from schemas.schemas import AssessmentReport, DashboardStats
from services.reporting import build_assessment_report, generate_faculty_report_pdf

router = APIRouter(prefix="/api", tags=["reports"])


def _load_assessment_for_report(db: Session, assessment_id: int) -> Assessment:
    assessment = (
        db.query(Assessment)
        .options(
            joinedload(Assessment.questions)
            .joinedload(Question.submissions)
            .joinedload(Submission.extracted_answer),
            joinedload(Assessment.questions)
            .joinedload(Question.submissions)
            .joinedload(Submission.criterion_results)
            .joinedload(CriterionResult.criterion),
            joinedload(Assessment.questions)
            .joinedload(Question.submissions)
            .joinedload(Submission.criterion_results)
            .joinedload(CriterionResult.review),
        )
        .filter(Assessment.id == assessment_id)
        .first()
    )
    if assessment is None:
        raise HTTPException(404, "Assessment not found")
    return assessment


@router.get("/reports/{assessment_id}", response_model=AssessmentReport)
def get_report(
    assessment_id: int, student_identifier: str | None = None, db: Session = Depends(get_db)
) -> AssessmentReport:
    assessment = _load_assessment_for_report(db, assessment_id)
    return build_assessment_report(db, assessment, config, student_identifier)


@router.get("/reports/{assessment_id}/pdf")
def get_report_pdf(
    assessment_id: int, student_identifier: str | None = None, db: Session = Depends(get_db)
):
    assessment = _load_assessment_for_report(db, assessment_id)
    safe_student = (student_identifier or "all").replace("/", "_")
    output_path = config.storage.upload_dir / f"report_{assessment_id}_{safe_student}.pdf"
    generate_faculty_report_pdf(db, assessment, config, output_path, student_identifier)
    return FileResponse(output_path, media_type="application/pdf", filename=output_path.name)


@router.get("/dashboard/stats", response_model=DashboardStats)
def dashboard_stats(db: Session = Depends(get_db)) -> DashboardStats:
    submissions = (
        db.query(Submission)
        .options(
            joinedload(Submission.extracted_answer),
            joinedload(Submission.criterion_results),
        )
        .all()
    )
    graded = [s for s in submissions if s.criterion_results]

    pct_scores = []
    for s in graded:
        if s.question.max_marks:
            ai_total = sum(cr.marks for cr in s.criterion_results)
            pct_scores.append((ai_total / s.question.max_marks) * 100)

    all_results = [cr for s in graded for cr in s.criterion_results]
    reviews_completed = sum(1 for cr in all_results if cr.review is not None)
    reviews_required = sum(
        1
        for cr in all_results
        if cr.review is None and cr.grading_confidence < config.thresholds.grading_review_below
    )
    for s in graded:
        rc = s.extracted_answer.recognition_confidence if s.extracted_answer else 1.0
        if rc < config.thresholds.recognition_review_below:
            reviews_required += 1
        already_verified = bool(s.extracted_answer and s.extracted_answer.manually_corrected)
        if s.input_type == "handwritten" and config.ocr.handwriting_force_review and not already_verified:
            reviews_required += 1

    recognition_confidences = [
        s.extracted_answer.recognition_confidence for s in graded if s.extracted_answer
    ]
    grading_confidences = [cr.grading_confidence for cr in all_results]

    return DashboardStats(
        total_submissions=len(submissions),
        graded_submissions=len(graded),
        average_score_pct=round(sum(pct_scores) / len(pct_scores), 2) if pct_scores else None,
        questions_graded=len({s.question_id for s in graded}),
        reviews_required=reviews_required,
        reviews_completed=reviews_completed,
        average_recognition_confidence=(
            round(sum(recognition_confidences) / len(recognition_confidences), 3)
            if recognition_confidences
            else None
        ),
        average_grading_confidence=(
            round(sum(grading_confidences) / len(grading_confidences), 3)
            if grading_confidences
            else None
        ),
    )
