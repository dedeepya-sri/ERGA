"""
End-to-end integration tests via FastAPI's TestClient — exercises the real
HTTP API, a real SQLite database, real PDF text-layer extraction, and real
Tesseract OCR (nothing here is mocked). Uses subject domains (water cycle,
algorithms, cell biology) distinct from the unit tests' domains, to keep
demonstrating that the engine is general-purpose.

Expected numeric assertions below were checked against the actual pipeline
output (see the diagnostic scripts referenced in docs/methodology.md)
rather than hand-calculated, since TF-IDF/cosine arithmetic is easy to get
wrong by eye.
"""
from __future__ import annotations

import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database.db import get_db
from database.models import Base
from main import app

TEST_ENGINE = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(bind=TEST_ENGINE, autoflush=False, autocommit=False)

FONT_CANDIDATES = [
    r"C:\Windows\Fonts\arial.ttf",
    r"C:\Windows\Fonts\calibri.ttf",
    r"C:\Windows\Fonts\segoeui.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
]


def get_test_font(size: int):
    for font_path in FONT_CANDIDATES:
        if Path(font_path).exists():
            return ImageFont.truetype(font_path, size)
    return ImageFont.load_default()


@pytest.fixture()
def client():
    Base.metadata.create_all(bind=TEST_ENGINE)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=TEST_ENGINE)


def _make_pdf_bytes(text_lines: list[str]) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    y = 720
    for line in text_lines:
        c.drawString(72, y, line)
        y -= 20
    c.save()
    return buf.getvalue()


def _make_ocr_image_bytes(text: str) -> bytes:
    img = Image.new("RGB", (900, 150), color="white")
    draw = ImageDraw.Draw(img)
    font = get_test_font(32)
    draw.text((20, 50), text, fill="black", font=font)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_page_image(text_lines: list[str]) -> io.BytesIO:
    """
    Renders text onto a page-shaped image matching the *letter* page's own
    aspect ratio (612x792pt -> 0.773 w/h), not an arbitrary short strip.
    Embedding a short/wide image into a tall PDF page stretches it to
    fill the box, which visibly distorts the text and can wreck OCR
    accuracy — a real risk for any "photo pasted onto a page" PDF, and
    something the first version of this helper got wrong itself.
    """
    width = 1700
    height = round(width * letter[1] / letter[0])  # preserve the page's own aspect ratio
    img = Image.new("RGB", (width, height), color="white")
    draw = ImageDraw.Draw(img)
    font = get_test_font(42)
    y = 150
    for line in text_lines:
        draw.text((100, y), line, fill="black", font=font)
        y += 80
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


def _make_image_only_pdf_bytes(text_lines: list[str]) -> bytes:
    """A PDF with NO real text layer — the page content is a rendered
    image, simulating a scanned/photographed answer sheet saved as PDF."""
    img_buf = _make_page_image(text_lines)

    pdf_buf = io.BytesIO()
    c = canvas.Canvas(pdf_buf, pagesize=letter)
    from reportlab.lib.utils import ImageReader

    c.drawImage(ImageReader(img_buf), 0, 0, width=letter[0], height=letter[1])
    c.save()
    return pdf_buf.getvalue()


def _make_mixed_content_pdf_bytes(typed_lines: list[str], image_lines: list[str]) -> bytes:
    """Page 1: a real text layer. Page 2: image-only, no text layer — the
    exact shape that previously made extraction silently drop page 2
    (fixed by deciding text-layer-vs-OCR per page instead of by whole-
    document average character count)."""
    img_buf = _make_page_image(image_lines)

    pdf_buf = io.BytesIO()
    c = canvas.Canvas(pdf_buf, pagesize=letter)
    from reportlab.lib.utils import ImageReader

    y_pos = 720
    for line in typed_lines:
        c.drawString(72, y_pos, line)
        y_pos -= 20
    c.showPage()
    c.drawImage(ImageReader(img_buf), 0, 0, width=letter[0], height=letter[1])
    c.save()
    return pdf_buf.getvalue()


def test_health_reports_active_engines(client: TestClient):
    health = client.get("/api/health").json()
    assert health["status"] == "ok"
    # This build has no route to a model hub, so the classical engines must
    # be what's actually active — never silently claim otherwise.
    assert health["embedding_engine"] == "tfidf"
    assert health["nli_engine"] == "lexical"


def test_full_grading_workflow_typed_answer(client: TestClient):
    assessment = client.post(
        "/api/assessments", json={"name": "Earth Science Quiz", "subject": "Geography"}
    ).json()

    question_payload = {
        "question_text": "Explain the water cycle and name at least three of its stages.",
        "max_marks": 10,
        "criteria": [
            {
                "description": "Defines the water cycle as the continuous movement of water through the environment",
                "marks": 4,
                "reference_concepts": ["continuous circulation"],
            },
            {
                "description": "Names at least three stages such as evaporation, condensation, and precipitation",
                "marks": 4,
                "reference_concepts": ["evaporation", "condensation", "precipitation"],
            },
            {
                "description": "Explains why the water cycle matters for ecosystems",
                "marks": 2,
                "reference_concepts": [],
            },
        ],
    }
    question = client.post(
        f"/api/assessments/{assessment['id']}/questions", json=question_payload
    ).json()
    assert len(question["criteria"]) == 3
    c1_id, c2_id, c3_id = (c["id"] for c in question["criteria"])

    # Answer fully covers C1 and C2, but never addresses ecosystem importance (C3).
    answer_text = (
        "The water cycle is the continuous movement of water through the environment. "
        "Its main stages are evaporation, condensation, and precipitation."
    )
    submission = client.post(
        "/api/submissions",
        data={
            "question_id": question["id"],
            "input_type": "typed",
            "student_identifier": "student-042",
            "text": answer_text,
        },
    ).json()
    assert submission["input_type"] == "typed"

    result = client.post(f"/api/submissions/{submission['id']}/grade").json()
    assert result["total_marks"] == 10
    by_id = {c["criterion_id"]: c for c in result["criteria"]}
    c1, c2, c3 = by_id[c1_id], by_id[c2_id], by_id[c3_id]

    assert c1["status"] == "supported"
    assert c1["marks"] == 4
    assert c1["evidence"], "evidence must be a real quote from the answer, not fabricated"
    assert c1["evidence"][0]["text"] in answer_text

    assert c2["status"] == "supported"
    assert c2["marks"] == 4

    # C3 is never addressed in the answer. The lexical engine still finds
    # *topical* overlap ("water", "cycle") even though the specific content
    # ("ecosystem", "matters") is absent, so it lands as a low-confidence
    # partial rather than a clean zero — an honest limitation of bag-of-
    # words matching (it sees shared subject vocabulary, not specific
    # relevance), and exactly the gap a true semantic/transformer NLI
    # engine would close. See docs/methodology.md.
    assert c3["status"] in ("partially_supported", "not_supported")
    assert c3["marks"] < c3["max_marks"]
    assert "ecosystem" in " ".join(c3["missing_concepts"])

    assert result["awarded_marks"] == round(c1["marks"] + c2["marks"] + c3["marks"], 2)
    assert result["final_marks"] == result["awarded_marks"]  # no faculty override yet
    # C2's grading confidence is legitimately shaky here (the rubric says
    # "at least three" but the student never writes the numeral), so the
    # system should route this for a human sanity-check.
    assert result["review_required"] is True

    fetched = client.get(f"/api/submissions/{submission['id']}/result").json()
    assert fetched["awarded_marks"] == result["awarded_marks"]

    # Faculty reviews the flagged criterion (Section 24's audit trail).
    review = client.post(
        "/api/reviews",
        json={
            "criterion_result_id": c3["id"],
            "faculty_marks": c3["max_marks"],
            "reason": "Student's accompanying diagram (not captured in text) covered ecosystem relevance",
            "reviewer": "Prof. Rao",
        },
    ).json()
    assert review["ai_marks"] == c3["marks"]
    assert review["faculty_marks"] == c3["max_marks"]

    updated = client.get(f"/api/submissions/{submission['id']}/result").json()
    assert updated["final_marks"] == round(c1["marks"] + c2["marks"] + c3["max_marks"], 2)
    assert updated["awarded_marks"] == result["awarded_marks"]  # AI's original number never mutates

    report = client.get(
        f"/api/reports/{assessment['id']}", params={"student_identifier": "student-042"}
    ).json()
    assert report["total_final_marks"] == updated["final_marks"]
    assert report["percentage"] == round(updated["final_marks"] / 10 * 100, 2)

    pdf_response = client.get(
        f"/api/reports/{assessment['id']}/pdf", params={"student_identifier": "student-042"}
    )
    assert pdf_response.status_code == 200
    assert pdf_response.content[:4] == b"%PDF"

    stats = client.get("/api/dashboard/stats").json()
    assert stats["total_submissions"] >= 1
    assert stats["graded_submissions"] >= 1


def test_rubric_must_sum_to_max_marks(client: TestClient):
    assessment = client.post("/api/assessments", json={"name": "Quick Quiz"}).json()
    bad_payload = {
        "question_text": "What is an algorithm?",
        "max_marks": 10,
        "criteria": [
            {"description": "Defines algorithm as a step-by-step procedure", "marks": 4},
            {"description": "Gives an example of an algorithm", "marks": 4},  # sums to 8, not 10
        ],
    }
    response = client.post(f"/api/assessments/{assessment['id']}/questions", json=bad_payload)
    assert response.status_code == 422


def test_pdf_text_layer_extraction(client: TestClient):
    assessment = client.post("/api/assessments", json={"name": "CS Basics"}).json()
    question = client.post(
        f"/api/assessments/{assessment['id']}/questions",
        json={
            "question_text": "What is an algorithm?",
            "max_marks": 10,
            "criteria": [
                {
                    "description": "Defines an algorithm as a step-by-step procedure for solving a problem",
                    "marks": 5,
                },
                {"description": "Gives a concrete example of an algorithm", "marks": 5},
            ],
        },
    ).json()

    pdf_bytes = _make_pdf_bytes(
        [
            "An algorithm is a step by step procedure for solving a problem.",
            "A recipe for baking bread is an everyday example of an algorithm.",
        ]
    )
    submission = client.post(
        "/api/submissions",
        data={"question_id": question["id"], "input_type": "pdf"},
        files={"file": ("answer.pdf", pdf_bytes, "application/pdf")},
    ).json()

    extracted = client.post(f"/api/submissions/{submission['id']}/extract").json()
    assert "algorithm" in extracted["text"].lower()
    assert "recipe" in extracted["text"].lower()
    assert extracted["recognition_confidence"] == 1.0  # genuine PDF text layer, nothing to "recognize"
    assert extracted["engine"] == "pdf-text-layer"

    graded = client.post(f"/api/submissions/{submission['id']}/grade").json()
    assert graded["awarded_marks"] > 0


def test_pdf_with_no_text_layer_falls_back_to_ocr(client: TestClient):
    """
    Regression test: a PDF whose page content is an image (e.g. a scanned
    or phone-photographed answer sheet saved as PDF, with no embedded text
    at all) must still be readable — the extraction must detect the
    missing text layer and fall back to rendering the page and running
    OCR on it, the same as an uploaded image would.
    """
    assessment = client.post("/api/assessments", json={"name": "Scanned PDF Test"}).json()
    question = client.post(
        f"/api/assessments/{assessment['id']}/questions",
        json={
            "question_text": "What is an algorithm?",
            "max_marks": 10,
            "criteria": [
                {"description": "Defines an algorithm as a step-by-step procedure", "marks": 5},
                {"description": "Gives a concrete example of an algorithm", "marks": 5},
            ],
        },
    ).json()

    pdf_bytes = _make_image_only_pdf_bytes(
        [
            "An algorithm is a step by step procedure for solving a problem.",
            "A recipe for baking bread is an everyday example of an algorithm.",
        ]
    )
    submission = client.post(
        "/api/submissions",
        data={"question_id": question["id"], "input_type": "pdf"},
        files={"file": ("scanned_answer.pdf", pdf_bytes, "application/pdf")},
    ).json()

    extracted = client.post(f"/api/submissions/{submission['id']}/extract").json()
    assert extracted["engine"].startswith("tesseract"), (
        f"expected the OCR fallback to trigger for a PDF with no text layer, got engine={extracted['engine']!r}"
    )
    assert "algorithm" in extracted["text"].lower()
    assert "recipe" in extracted["text"].lower()
    # Real OCR bounding boxes must be present (Section 25) — not None,
    # which would mean the text-layer path was wrongly taken instead.
    assert extracted["source_detail"]["lines"][0]["bbox"] is not None

    graded = client.post(f"/api/submissions/{submission['id']}/grade").json()
    assert graded["awarded_marks"] > 0


def test_pdf_mixed_typed_and_scanned_pages_keeps_both(client: TestClient):
    """
    Regression test for a real bug found while investigating a report that
    PDF uploads were "not being considered": a PDF where only *some* pages
    have a text layer (e.g. page 1 typed, page 2 a pasted-in scan/photo of
    a diagram or handwritten continuation) used to be judged by a single
    whole-document average characters-per-page, which could clear the bar
    even though a specific page had zero extractable text — silently
    dropping that page's content from grading entirely. Extraction must
    now decide per page, so every page's content survives.
    """
    assessment = client.post("/api/assessments", json={"name": "Mixed PDF Test"}).json()
    question = client.post(
        f"/api/assessments/{assessment['id']}/questions",
        json={
            "question_text": "What is an algorithm? Give an example.",
            "max_marks": 10,
            "criteria": [
                {"description": "Defines an algorithm as a step-by-step procedure", "marks": 5},
                {"description": "Gives a concrete example of an algorithm, such as a recipe", "marks": 5},
            ],
        },
    ).json()

    pdf_bytes = _make_mixed_content_pdf_bytes(
        typed_lines=["An algorithm is a step by step procedure for solving a problem."],
        image_lines=["A recipe for baking bread is an everyday example of an algorithm."],
    )
    submission = client.post(
        "/api/submissions",
        data={"question_id": question["id"], "input_type": "pdf"},
        files={"file": ("mixed_answer.pdf", pdf_bytes, "application/pdf")},
    ).json()

    extracted = client.post(f"/api/submissions/{submission['id']}/extract").json()
    assert extracted["engine"] == "tesseract:pdf-mixed"
    assert "algorithm" in extracted["text"].lower()
    assert "recipe" in extracted["text"].lower(), (
        "page 2's content was dropped — this is the exact bug this test guards against"
    )

    lines = extracted["source_detail"]["lines"]
    page1_lines = [l for l in lines if l["page"] == 1]
    page2_lines = [l for l in lines if l["page"] == 2]
    assert page1_lines and page1_lines[0]["bbox"] is None  # text-layer page: no bbox
    assert page2_lines and page2_lines[0]["bbox"] is not None  # OCR page: real bbox

    graded = client.post(f"/api/submissions/{submission['id']}/grade").json()
    by_id = {c["criterion_id"]: c for c in graded["criteria"]}
    criteria_ids = [c["id"] for c in question["criteria"]]
    assert by_id[criteria_ids[1]]["status"] != "not_supported", (
        "the example-criterion should be satisfied by page 2's content, which must not be dropped"
    )


def test_image_ocr_extraction_and_correction(client: TestClient):
    assessment = client.post("/api/assessments", json={"name": "Scanned Answers"}).json()
    question = client.post(
        f"/api/assessments/{assessment['id']}/questions",
        json={
            "question_text": "Name the powerhouse of the cell.",
            "max_marks": 2,
            "criteria": [{"description": "Names the mitochondria as the powerhouse of the cell", "marks": 2}],
        },
    ).json()

    image_bytes = _make_ocr_image_bytes("The mitochondria is the powerhouse of the cell")
    submission = client.post(
        "/api/submissions",
        data={"question_id": question["id"], "input_type": "scan"},
        files={"file": ("answer.png", image_bytes, "image/png")},
    ).json()

    extracted = client.post(f"/api/submissions/{submission['id']}/extract").json()
    assert extracted["engine"].startswith("tesseract")
    assert "mitochondria" in extracted["text"].lower()
    assert 0.0 <= extracted["recognition_confidence"] <= 1.0
    # Real bounding box from Tesseract, not fabricated (Section 25).
    assert extracted["source_detail"]["lines"][0]["bbox"]["width"] > 0

    # Faculty reviews and (redundantly, but exercising Section 22's flow)
    # confirms the OCR'd text before grading.
    corrected = client.put(
        f"/api/submissions/{submission['id']}/extracted-text",
        json={"text": "The mitochondria is the powerhouse of the cell."},
    ).json()
    assert corrected["manually_corrected"] is True
    assert corrected["recognition_confidence"] == 1.0

    graded = client.post(f"/api/submissions/{submission['id']}/grade").json()
    assert graded["criteria"][0]["status"] == "supported"
    assert graded["review_required"] is False


def test_handwritten_input_always_flagged_for_review(client: TestClient):
    assessment = client.post("/api/assessments", json={"name": "Handwritten Quiz"}).json()
    question = client.post(
        f"/api/assessments/{assessment['id']}/questions",
        json={
            "question_text": "Name the powerhouse of the cell.",
            "max_marks": 2,
            "criteria": [{"description": "Names the mitochondria as the powerhouse of the cell", "marks": 2}],
        },
    ).json()

    image_bytes = _make_ocr_image_bytes("The mitochondria is the powerhouse of the cell")
    submission = client.post(
        "/api/submissions",
        data={"question_id": question["id"], "input_type": "handwritten"},
        files={"file": ("answer.png", image_bytes, "image/png")},
    ).json()
    client.post(f"/api/submissions/{submission['id']}/extract")
    graded = client.post(f"/api/submissions/{submission['id']}/grade").json()

    # Even though this "handwriting" is actually clean rendered text (and
    # would score confidently on recognition alone), handwritten input is
    # unconditionally routed to review — Section 36: "Don't pretend OCR is
    # perfect."
    assert graded["review_required"] is True
    assert any("Handwritten" in r for r in graded["review_reasons"])


def test_submission_deletion(client: TestClient):
    assessment = client.post("/api/assessments", json={"name": "Temp"}).json()
    question = client.post(
        f"/api/assessments/{assessment['id']}/questions",
        json={"question_text": "Q", "max_marks": 2, "criteria": [{"description": "d", "marks": 2}]},
    ).json()
    submission = client.post(
        "/api/submissions",
        data={"question_id": question["id"], "input_type": "typed", "text": "answer text"},
    ).json()
    assert client.delete(f"/api/submissions/{submission['id']}").status_code == 204
    assert client.get(f"/api/submissions/{submission['id']}").status_code == 404


def _make_encrypted_pdf_bytes() -> bytes:
    from reportlab.lib.pdfencrypt import StandardEncryption

    buf = io.BytesIO()
    enc = StandardEncryption("userpass", ownerPassword="ownerpass", canPrint=1)
    c = canvas.Canvas(buf, pagesize=letter, encrypt=enc)
    c.drawString(72, 720, "This is a secret answer.")
    c.save()
    return buf.getvalue()


def test_password_protected_pdf_gives_clear_error(client: TestClient):
    """
    Regression test: a password-protected PDF used to surface as an EMPTY
    error message ("Extraction failed: ") — which reads to a user as if
    nothing went wrong, i.e. exactly the kind of silent-looking failure
    this whole investigation was about. It must now give a specific,
    actionable message.
    """
    assessment = client.post("/api/assessments", json={"name": "Encrypted PDF Test"}).json()
    question = client.post(
        f"/api/assessments/{assessment['id']}/questions",
        json={"question_text": "Q", "max_marks": 2, "criteria": [{"description": "d", "marks": 2}]},
    ).json()
    submission = client.post(
        "/api/submissions",
        data={"question_id": question["id"], "input_type": "pdf"},
        files={"file": ("encrypted.pdf", _make_encrypted_pdf_bytes(), "application/pdf")},
    ).json()

    response = client.post(f"/api/submissions/{submission['id']}/extract")
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail, "error message must not be empty"
    assert "password" in detail.lower()


def test_corrupted_pdf_gives_clear_error(client: TestClient):
    assessment = client.post("/api/assessments", json={"name": "Corrupted PDF Test"}).json()
    question = client.post(
        f"/api/assessments/{assessment['id']}/questions",
        json={"question_text": "Q", "max_marks": 2, "criteria": [{"description": "d", "marks": 2}]},
    ).json()
    garbage = b"%PDF-1.4\nthis is not a real pdf structure at all, just bytes"
    submission = client.post(
        "/api/submissions",
        data={"question_id": question["id"], "input_type": "pdf"},
        files={"file": ("corrupted.pdf", garbage, "application/pdf")},
    ).json()

    response = client.post(f"/api/submissions/{submission['id']}/extract")
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail, "error message must not be empty"
    assert "corrupted" in detail.lower() or "valid pdf" in detail.lower()

