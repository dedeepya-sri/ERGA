"""Assessment + question/rubric endpoints (Sections 20, 21, 41)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from database.db import get_db
from database.models import Assessment, Question, RubricCriterion
from schemas.schemas import (
    AssessmentCreate,
    AssessmentDetail,
    AssessmentOut,
    QuestionCreate,
    QuestionOut,
    RubricCriterionCreate,
    RubricValidation,
)

router = APIRouter(prefix="/api", tags=["assessments"])

MARKS_TOLERANCE = 0.01


def _validate_rubric(criteria_marks: list[float], max_marks: float) -> RubricValidation:
    """Section 21: 'Validate that: SUM(criteria marks) = maximum marks'."""
    total = round(sum(criteria_marks), 2)
    diff = round(total - max_marks, 2)
    valid = abs(diff) <= MARKS_TOLERANCE
    if valid:
        message = "Rubric marks sum to the question's maximum marks."
    else:
        direction = "over" if diff > 0 else "under"
        message = (
            f"Criteria sum to {total:g}, but the question is worth {max_marks:g} "
            f"({direction} by {abs(diff):g})."
        )
    return RubricValidation(valid=valid, sum_marks=total, max_marks=max_marks, difference=diff, message=message)


@router.post("/assessments", response_model=AssessmentOut, status_code=201)
def create_assessment(payload: AssessmentCreate, db: Session = Depends(get_db)) -> Assessment:
    assessment = Assessment(name=payload.name, subject=payload.subject)
    db.add(assessment)
    db.commit()
    db.refresh(assessment)
    return assessment


@router.get("/assessments", response_model=list[AssessmentOut])
def list_assessments(db: Session = Depends(get_db)) -> list[Assessment]:
    return db.query(Assessment).order_by(Assessment.created_at.desc()).all()


@router.get("/assessments/{assessment_id}", response_model=AssessmentDetail)
def get_assessment(assessment_id: int, db: Session = Depends(get_db)) -> Assessment:
    assessment = (
        db.query(Assessment)
        .options(joinedload(Assessment.questions).joinedload(Question.criteria))
        .filter(Assessment.id == assessment_id)
        .first()
    )
    if assessment is None:
        raise HTTPException(404, "Assessment not found")
    return assessment


@router.delete("/assessments/{assessment_id}", status_code=204)
def delete_assessment(assessment_id: int, db: Session = Depends(get_db)) -> None:
    assessment = db.query(Assessment).filter(Assessment.id == assessment_id).first()
    if assessment is None:
        raise HTTPException(404, "Assessment not found")
    db.delete(assessment)
    db.commit()


@router.post("/assessments/{assessment_id}/questions", response_model=QuestionOut, status_code=201)
def create_question(assessment_id: int, payload: QuestionCreate, db: Session = Depends(get_db)) -> Question:
    assessment = db.query(Assessment).filter(Assessment.id == assessment_id).first()
    if assessment is None:
        raise HTTPException(404, "Assessment not found")

    if payload.criteria:
        validation = _validate_rubric([c.marks for c in payload.criteria], payload.max_marks)
        if not validation.valid:
            raise HTTPException(422, validation.message)

    question = Question(
        assessment_id=assessment_id, question_text=payload.question_text, max_marks=payload.max_marks
    )
    db.add(question)
    db.flush()

    for i, c in enumerate(payload.criteria):
        db.add(
            RubricCriterion(
                question_id=question.id,
                description=c.description,
                marks=c.marks,
                reference_concepts=c.reference_concepts,
                order_index=i,
            )
        )
    db.commit()
    db.refresh(question)
    return question


@router.get("/questions/{question_id}", response_model=QuestionOut)
def get_question(question_id: int, db: Session = Depends(get_db)) -> Question:
    question = (
        db.query(Question)
        .options(joinedload(Question.criteria))
        .filter(Question.id == question_id)
        .first()
    )
    if question is None:
        raise HTTPException(404, "Question not found")
    return question


@router.put("/questions/{question_id}/criteria", response_model=QuestionOut)
def replace_criteria(
    question_id: int, criteria: list[RubricCriterionCreate], db: Session = Depends(get_db)
) -> Question:
    question = db.query(Question).filter(Question.id == question_id).first()
    if question is None:
        raise HTTPException(404, "Question not found")

    validation = _validate_rubric([c.marks for c in criteria], question.max_marks)
    if not validation.valid:
        raise HTTPException(422, validation.message)

    db.query(RubricCriterion).filter(RubricCriterion.question_id == question_id).delete()
    for i, c in enumerate(criteria):
        db.add(
            RubricCriterion(
                question_id=question_id,
                description=c.description,
                marks=c.marks,
                reference_concepts=c.reference_concepts,
                order_index=i,
            )
        )
    db.commit()
    db.refresh(question)
    return question


@router.post("/questions/{question_id}/rubric/validate", response_model=RubricValidation)
def validate_rubric(
    question_id: int, criteria: list[RubricCriterionCreate], db: Session = Depends(get_db)
) -> RubricValidation:
    """Lets the Rubric Builder UI live-validate SUM(marks) as faculty type, before saving."""
    question = db.query(Question).filter(Question.id == question_id).first()
    if question is None:
        raise HTTPException(404, "Question not found")
    return _validate_rubric([c.marks for c in criteria], question.max_marks)
