"""
Report generation.

`build_assessment_report` produces the aggregate structure described in
Sections 19/48: per-question AI/final marks, total, percentage, and which
criteria are flagged for review.

`generate_faculty_report_pdf` produces the downloadable PDF described in
Section 49 (student ID, question, rubric, criterion scores, evidence,
missing concepts, confidence, AI recommendation, faculty correction, final
score) using reportlab, per the pdf skill's guidance for this environment.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy.orm import Session

from config.settings import Config
from database.models import Assessment, Submission
from schemas.schemas import AssessmentReport, QuestionReportEntry
from services.confidence import criterion_review_reasons


def _latest_graded_submission(question, student_identifier: str | None) -> Submission | None:
    candidates = [
        s for s in question.submissions
        if student_identifier is None or s.student_identifier == student_identifier
    ]
    graded = [s for s in candidates if s.criterion_results]
    return max(graded, key=lambda s: s.id) if graded else None


def _submission_marks_and_flags(
    submission: Submission, question_id: int, config: Config
) -> tuple[float, float, list[str]]:
    ai_total = 0.0
    final_total = 0.0
    flagged: list[str] = []

    for cr in submission.criterion_results:
        ai_total += cr.marks
        final_total += cr.review.faculty_marks if cr.review else cr.marks

        if cr.review is None:
            reasons = criterion_review_reasons(
                f"Q{question_id} C{cr.criterion_id}", cr.grading_confidence, config.thresholds
            )
            flagged.extend(reasons)

    rc = submission.extracted_answer.recognition_confidence if submission.extracted_answer else 1.0
    if rc < config.thresholds.recognition_review_below:
        flagged.append(f"Q{question_id}: low recognition confidence ({rc:.2f})")

    return round(ai_total, 2), round(final_total, 2), flagged


def build_assessment_report(
    db: Session, assessment: Assessment, config: Config, student_identifier: str | None = None
) -> AssessmentReport:
    entries: list[QuestionReportEntry] = []
    total_max = total_awarded = total_final = 0.0
    flagged_all: list[str] = []

    for question in sorted(assessment.questions, key=lambda q: q.id):
        total_max += question.max_marks
        submission = _latest_graded_submission(question, student_identifier)

        if submission is None:
            entries.append(
                QuestionReportEntry(
                    question_id=question.id,
                    question_text=question.question_text,
                    total_marks=question.max_marks,
                    awarded_marks=0.0,
                    final_marks=0.0,
                    review_required=False,
                    criteria_requiring_review=[],
                )
            )
            continue

        ai_awarded, final_marks, flagged = _submission_marks_and_flags(submission, question.id, config)
        total_awarded += ai_awarded
        total_final += final_marks
        flagged_all.extend(flagged)

        entries.append(
            QuestionReportEntry(
                question_id=question.id,
                question_text=question.question_text,
                total_marks=question.max_marks,
                awarded_marks=ai_awarded,
                final_marks=final_marks,
                review_required=bool(flagged),
                criteria_requiring_review=flagged,
            )
        )

    pct = round((total_final / total_max) * 100, 2) if total_max else 0.0

    return AssessmentReport(
        assessment_id=assessment.id,
        assessment_name=assessment.name,
        student_identifier=student_identifier,
        total_max_marks=round(total_max, 2),
        total_awarded_marks=round(total_awarded, 2),
        total_final_marks=round(total_final, 2),
        percentage=pct,
        questions=entries,
        flagged_for_review=flagged_all,
    )


# ------------------------------- PDF report ----------------------------------

_INK = colors.HexColor("#16213A")
_PAPER = colors.HexColor("#EFF1EC")


def generate_faculty_report_pdf(
    db: Session,
    assessment: Assessment,
    config: Config,
    output_path: Path,
    student_identifier: str | None = None,
) -> Path:
    report = build_assessment_report(db, assessment, config, student_identifier)

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("ERGATitle", parent=styles["Title"], fontSize=18, textColor=_INK)
    h2 = ParagraphStyle("ERGAH2", parent=styles["Heading2"], spaceBefore=16, spaceAfter=6, textColor=_INK)
    body = styles["Normal"]
    cell = ParagraphStyle("ERGACell", parent=styles["Normal"], fontSize=8, leading=10)

    doc = SimpleDocTemplate(
        str(output_path), pagesize=letter, topMargin=0.7 * inch, bottomMargin=0.7 * inch
    )
    story = [
        Paragraph(f"ERGA Faculty Report — {assessment.name}", title_style),
        Paragraph(
            f"Student: {student_identifier or 'All students (assessment summary)'}", body
        ),
        Paragraph(
            f"Generated: {dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}", body
        ),
        Spacer(1, 12),
    ]

    summary = Table(
        [
            ["Total possible", "AI awarded", "Final (with overrides)", "Percentage"],
            [
                f"{report.total_max_marks:g}",
                f"{report.total_awarded_marks:g}",
                f"{report.total_final_marks:g}",
                f"{report.percentage:g}%",
            ],
        ],
        hAlign="LEFT",
    )
    summary.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), _INK),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(summary)

    for question in sorted(assessment.questions, key=lambda q: q.id):
        submission = _latest_graded_submission(question, student_identifier)
        story.append(Paragraph(f"Q{question.id}. {question.question_text}", h2))

        if submission is None:
            story.append(Paragraph("Not yet graded.", body))
            continue

        rows = [["Criterion", "Status", "Marks", "Grading conf.", "Evidence / Missing concepts"]]
        for cr in sorted(submission.criterion_results, key=lambda c: c.criterion.order_index):
            status_label = cr.status.replace("_", " ").title()
            marks_label = f"{cr.marks:g} / {cr.max_marks:g}"
            if cr.review:
                marks_label += f"\n-> {cr.review.faculty_marks:g} (faculty: {cr.review.reason or 'override'})"
            ev_text = cr.evidence[0].text if cr.evidence else "(no matching evidence found)"
            if cr.missing_concepts:
                ev_text += f"\nMissing terms: {', '.join(cr.missing_concepts)}"
            rows.append(
                [
                    Paragraph(cr.criterion.description, cell),
                    status_label,
                    Paragraph(marks_label.replace("\n", "<br/>"), cell),
                    f"{cr.grading_confidence:.2f}",
                    Paragraph(ev_text.replace("\n", "<br/>"), cell),
                ]
            )

        table = Table(
            rows, colWidths=[1.5 * inch, 0.85 * inch, 0.95 * inch, 0.7 * inch, 2.4 * inch], hAlign="LEFT"
        )
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), _PAPER),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.append(table)
        story.append(Spacer(1, 10))

    if report.flagged_for_review:
        story.append(Paragraph("Flagged for faculty review", h2))
        for f in report.flagged_for_review:
            story.append(Paragraph(f"&bull; {f}", body))

    doc.build(story)
    return output_path
