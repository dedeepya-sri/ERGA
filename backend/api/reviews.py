"""Faculty review / override endpoints (Section 24) — every override is an audit record."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database.db import get_db
from database.models import CriterionResult, Review
from schemas.schemas import ReviewCreate, ReviewOut

router = APIRouter(prefix="/api/reviews", tags=["reviews"])


@router.post("", response_model=ReviewOut, status_code=201)
def create_review(payload: ReviewCreate, db: Session = Depends(get_db)) -> Review:
    cr = (
        db.query(CriterionResult)
        .filter(CriterionResult.id == payload.criterion_result_id)
        .first()
    )
    if cr is None:
        raise HTTPException(404, "Criterion result not found")
    if payload.faculty_marks > cr.max_marks:
        raise HTTPException(
            422,
            f"Faculty marks ({payload.faculty_marks:g}) exceed the criterion's "
            f"maximum ({cr.max_marks:g}).",
        )

    review = cr.review
    if review:
        review.faculty_marks = payload.faculty_marks
        review.reason = payload.reason
        review.reviewer = payload.reviewer
        # ai_marks and timestamp are left as originally recorded — the audit
        # trail should show what the AI first said, not get overwritten.
    else:
        review = Review(
            criterion_result_id=cr.id,
            ai_marks=cr.marks,
            faculty_marks=payload.faculty_marks,
            reason=payload.reason,
            reviewer=payload.reviewer,
        )
        db.add(review)

    db.commit()
    db.refresh(review)
    return review


@router.delete("/{criterion_result_id}", status_code=204)
def clear_review(criterion_result_id: int, db: Session = Depends(get_db)) -> None:
    """Revert a criterion back to the AI's original assessment."""
    review = db.query(Review).filter(Review.criterion_result_id == criterion_result_id).first()
    if review is None:
        raise HTTPException(404, "No review to clear for this criterion")
    db.delete(review)
    db.commit()
