"""
ORM models. Mirrors the database design in Section 40 of the project spec,
plus the extra tables needed to actually persist evidence and audit trails
(Evidence, Review) that the spec's narrative sections (17, 24, 25) require.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


class Assessment(Base):
    """A named collection of questions, e.g. "Midterm — Data Structures"."""

    __tablename__ = "assessments"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    subject = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=utcnow)

    questions = relationship(
        "Question", back_populates="assessment", cascade="all, delete-orphan"
    )


class Question(Base):
    """One exam question, with its rubric criteria and student submissions."""

    __tablename__ = "questions"

    id = Column(Integer, primary_key=True)
    assessment_id = Column(Integer, ForeignKey("assessments.id"), nullable=False)
    question_text = Column(Text, nullable=False)
    max_marks = Column(Float, nullable=False)
    created_at = Column(DateTime, default=utcnow)

    assessment = relationship("Assessment", back_populates="questions")
    criteria = relationship(
        "RubricCriterion",
        back_populates="question",
        cascade="all, delete-orphan",
        order_by="RubricCriterion.order_index",
    )
    submissions = relationship(
        "Submission", back_populates="question", cascade="all, delete-orphan"
    )


class RubricCriterion(Base):
    """A single scored criterion within a question's rubric. The rubric is authoritative."""

    __tablename__ = "rubric_criteria"

    id = Column(Integer, primary_key=True)
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=False)
    description = Column(Text, nullable=False)
    marks = Column(Float, nullable=False)
    reference_concepts = Column(JSON, default=list)  # list[str], optional keyword hints
    order_index = Column(Integer, default=0)

    question = relationship("Question", back_populates="criteria")


class Submission(Base):
    """One student's answer to one question, in any supported input format."""

    __tablename__ = "submissions"

    id = Column(Integer, primary_key=True)
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=False)
    student_identifier = Column(String(255), nullable=True)
    input_type = Column(String(32), nullable=False)  # typed | pdf | scan | handwritten
    file_path = Column(String(512), nullable=True)
    created_at = Column(DateTime, default=utcnow)

    question = relationship("Question", back_populates="submissions")
    extracted_answer = relationship(
        "ExtractedAnswer",
        back_populates="submission",
        uselist=False,
        cascade="all, delete-orphan",
    )
    criterion_results = relationship(
        "CriterionResult", back_populates="submission", cascade="all, delete-orphan"
    )


class ExtractedAnswer(Base):
    """
    The normalized text representation for a submission (Section 6), whatever
    the original input format was, plus the recognition confidence and raw
    per-word detail needed for traceability (Section 25).
    """

    __tablename__ = "extracted_answers"

    id = Column(Integer, primary_key=True)
    submission_id = Column(Integer, ForeignKey("submissions.id"), nullable=False)
    text = Column(Text, nullable=False, default="")
    recognition_confidence = Column(Float, nullable=False, default=1.0)
    manually_corrected = Column(Boolean, default=False)
    engine = Column(String(64), nullable=True)  # "typed" | "pdf-text" | "tesseract-ocr" | ...
    # Per-page / per-word detail: {"pages": [...], "words": [{text, conf, page, bbox}, ...]}
    source_detail = Column(JSON, default=dict)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    submission = relationship("Submission", back_populates="extracted_answer")


class CriterionResult(Base):
    """The grading engine's assessment of one criterion for one submission."""

    __tablename__ = "criterion_results"

    id = Column(Integer, primary_key=True)
    submission_id = Column(Integer, ForeignKey("submissions.id"), nullable=False)
    criterion_id = Column(Integer, ForeignKey("rubric_criteria.id"), nullable=False)
    status = Column(String(32), nullable=False)  # supported | partially_supported | not_supported
    marks = Column(Float, nullable=False)
    max_marks = Column(Float, nullable=False)
    composite_score = Column(Float, nullable=False)  # raw NLI composite before thresholding
    grading_confidence = Column(Float, nullable=False)
    missing_concepts = Column(JSON, default=list)  # list[str]
    engine_info = Column(JSON, default=dict)  # which embedder/nli engine + version produced this

    submission = relationship("Submission", back_populates="criterion_results")
    criterion = relationship("RubricCriterion")
    evidence = relationship(
        "Evidence", back_populates="criterion_result", cascade="all, delete-orphan"
    )
    review = relationship(
        "Review",
        back_populates="criterion_result",
        uselist=False,
        cascade="all, delete-orphan",
    )


class Evidence(Base):
    """
    A single retrieved answer segment supporting (or failing to support) a
    criterion. Text is always a verbatim substring of the extracted answer —
    never generated (Section 36: "Do not fabricate evidence").
    """

    __tablename__ = "evidence"

    id = Column(Integer, primary_key=True)
    criterion_result_id = Column(Integer, ForeignKey("criterion_results.id"), nullable=False)
    text = Column(Text, nullable=False)
    similarity = Column(Float, nullable=False)
    segment_index = Column(Integer, nullable=True)
    page = Column(Integer, nullable=True)
    bbox = Column(JSON, nullable=True)  # null unless the OCR engine actually returned one

    criterion_result = relationship("CriterionResult", back_populates="evidence")


class Review(Base):
    """Faculty override of one criterion's AI-assigned marks (Section 24 audit trail)."""

    __tablename__ = "reviews"

    id = Column(Integer, primary_key=True)
    criterion_result_id = Column(
        Integer, ForeignKey("criterion_results.id"), nullable=False, unique=True
    )
    ai_marks = Column(Float, nullable=False)
    faculty_marks = Column(Float, nullable=False)
    reason = Column(Text, nullable=True)
    reviewer = Column(String(255), nullable=True)
    timestamp = Column(DateTime, default=utcnow)

    criterion_result = relationship("CriterionResult", back_populates="review")
