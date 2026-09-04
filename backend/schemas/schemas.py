"""Pydantic schemas for API request/response bodies."""
from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

InputType = Literal["typed", "pdf", "scan", "handwritten"]
CriterionStatus = Literal["supported", "partially_supported", "not_supported"]


# ----------------------------- Rubric / Question ---------------------------


class RubricCriterionCreate(BaseModel):
    description: str
    marks: float = Field(gt=0)
    reference_concepts: list[str] = Field(default_factory=list)


class RubricCriterionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    description: str
    marks: float
    reference_concepts: list[str]
    order_index: int


class QuestionCreate(BaseModel):
    question_text: str
    max_marks: float = Field(gt=0)
    criteria: list[RubricCriterionCreate] = Field(default_factory=list)

    @field_validator("criteria")
    @classmethod
    def criteria_not_empty_if_provided(cls, v: list[RubricCriterionCreate]) -> list[RubricCriterionCreate]:
        return v


class QuestionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    assessment_id: int
    question_text: str
    max_marks: float
    criteria: list[RubricCriterionOut]


class RubricValidation(BaseModel):
    valid: bool
    sum_marks: float
    max_marks: float
    difference: float
    message: str


# ------------------------------- Assessment ---------------------------------


class AssessmentCreate(BaseModel):
    name: str
    subject: str | None = None


class AssessmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    subject: str | None
    created_at: dt.datetime


class AssessmentDetail(AssessmentOut):
    questions: list[QuestionOut]


# ------------------------------- Submission ----------------------------------


class TypedSubmissionCreate(BaseModel):
    question_id: int
    text: str
    student_identifier: str | None = None


class SubmissionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    question_id: int
    student_identifier: str | None
    input_type: InputType
    file_path: str | None
    created_at: dt.datetime


class WordBox(BaseModel):
    text: str
    confidence: float
    page: int
    left: float
    top: float
    width: float
    height: float


class ExtractedAnswerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    submission_id: int
    text: str
    recognition_confidence: float
    manually_corrected: bool
    engine: str | None
    source_detail: dict


class ExtractedTextUpdate(BaseModel):
    text: str


# ------------------------------- Grading result -------------------------------


class EvidenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    text: str
    similarity: float
    segment_index: int | None
    page: int | None
    bbox: dict | None


class ReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ai_marks: float
    faculty_marks: float
    reason: str | None
    reviewer: str | None
    timestamp: dt.datetime


class CriterionResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    criterion_id: int
    description: str
    status: CriterionStatus
    marks: float
    max_marks: float
    composite_score: float
    grading_confidence: float
    missing_concepts: list[str]
    evidence: list[EvidenceOut]
    review: ReviewOut | None = None
    engine_info: dict


class GradingResultOut(BaseModel):
    submission_id: int
    question_id: int
    question_text: str
    total_marks: float
    awarded_marks: float
    final_marks: float  # awarded_marks, with any faculty overrides applied
    recognition_confidence: float
    grading_confidence: float  # min across criteria — the weakest link
    review_required: bool
    review_reasons: list[str]
    criteria: list[CriterionResultOut]


# --------------------------------- Reviews -------------------------------------


class ReviewCreate(BaseModel):
    criterion_result_id: int
    faculty_marks: float = Field(ge=0)
    reason: str | None = None
    reviewer: str | None = None


# --------------------------------- Reports --------------------------------------


class QuestionReportEntry(BaseModel):
    question_id: int
    question_text: str
    total_marks: float
    awarded_marks: float
    final_marks: float
    review_required: bool
    criteria_requiring_review: list[str]


class AssessmentReport(BaseModel):
    assessment_id: int
    assessment_name: str
    student_identifier: str | None
    total_max_marks: float
    total_awarded_marks: float
    total_final_marks: float
    percentage: float
    questions: list[QuestionReportEntry]
    flagged_for_review: list[str]


class DashboardStats(BaseModel):
    total_submissions: int
    graded_submissions: int
    average_score_pct: float | None
    questions_graded: int
    reviews_required: int
    reviews_completed: int
    average_recognition_confidence: float | None
    average_grading_confidence: float | None
