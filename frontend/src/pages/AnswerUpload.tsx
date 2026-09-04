import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type { ExtractedAnswer, InputType, Question, Submission } from "../api/types";
import { ErrorNotice, Spinner } from "../components/Shared";

const TABS: { id: InputType; label: string; hint: string }[] = [
  { id: "typed", label: "Paste answer", hint: "Type or paste the student's answer directly." },
  { id: "pdf", label: "Upload PDF", hint: "A typed answer exported to PDF, or a scanned PDF." },
  { id: "scan", label: "Upload scanned image", hint: "A photo or scan of a printed/typed answer sheet." },
  { id: "handwritten", label: "Upload handwritten answer", hint: "A photo or scan of handwriting." },
];

export default function AnswerUpload() {
  const { questionId } = useParams();
  const id = Number(questionId);
  const navigate = useNavigate();

  const [question, setQuestion] = useState<Question | null>(null);
  const [tab, setTab] = useState<InputType>("typed");
  const [studentId, setStudentId] = useState("");
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [submission, setSubmission] = useState<Submission | null>(null);
  const [extracted, setExtracted] = useState<ExtractedAnswer | null>(null);
  const [editedText, setEditedText] = useState("");

  const imagePreviewUrl = useMemo(() => (file && tab !== "pdf" ? URL.createObjectURL(file) : null), [file, tab]);

  useEffect(() => {
    api.getQuestion(id).then(setQuestion);
  }, [id]);

  async function handleUploadTyped() {
    setError(null);
    if (!text.trim()) {
      setError("Enter the student's answer text first.");
      return;
    }
    setBusy(true);
    try {
      const sub = await api.createTypedSubmission({
        question_id: id,
        text: text.trim(),
        student_identifier: studentId.trim() || undefined,
      });
      setSubmission(sub);
      // Typed submissions already have an ExtractedAnswer created
      // server-side (recognition_confidence=1.0, nothing to recognize) —
      // just read it back.
      const ex = await api.getExtractedText(sub.id);
      setExtracted(ex);
      setEditedText(ex.text);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function handleUploadFile() {
    setError(null);
    if (!file) {
      setError("Choose a file first.");
      return;
    }
    setBusy(true);
    try {
      const sub = await api.createFileSubmission({
        question_id: id,
        input_type: tab as "pdf" | "scan" | "handwritten",
        file,
        student_identifier: studentId.trim() || undefined,
      });
      try {
        const ex = await api.extractSubmission(sub.id);
        setSubmission(sub);
        setExtracted(ex);
        setEditedText(ex.text);
      } catch (extractErr) {
        // Upload succeeded but extraction failed (e.g. password-protected
        // PDF, corrupted file, OCR engine unavailable) — clean up the
        // now-useless submission and stay on the upload form with a clear
        // error, rather than dropping the user into a "review" screen
        // with an empty textarea and no obvious way back.
        await api.deleteSubmission(sub.id).catch(() => undefined);
        throw extractErr;
      }
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function handleSaveCorrection() {
    if (!submission) return;
    setBusy(true);
    setError(null);
    try {
      const ex = await api.correctExtractedText(submission.id, editedText);
      setExtracted(ex);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function handleGrade() {
    if (!submission) return;
    setBusy(true);
    setError(null);
    try {
      if (extracted && editedText !== extracted.text) {
        await api.correctExtractedText(submission.id, editedText);
      }
      await api.gradeSubmission(submission.id);
      navigate(`/submissions/${submission.id}/result`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  function resetToInput() {
    setSubmission(null);
    setExtracted(null);
    setEditedText("");
    setFile(null);
    setText("");
  }

  if (!question)
    return (
      <div className="empty-state">
        <Spinner /> Loading…
      </div>
    );

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="page-eyebrow">
            <Link to={`/assessments/${question.assessment_id}`}>← Back to assessment</Link>
          </div>
          <h1>Submit an answer</h1>
          <p className="page-subtitle">“{question.question_text}”</p>
        </div>
      </div>

      {error && <ErrorNotice message={error} />}

      {!submission ? (
        <div className="card">
          <div className="field" style={{ maxWidth: 280 }}>
            <label className="field-label">Student identifier (optional)</label>
            <input
              className="input"
              placeholder="e.g. student-042"
              value={studentId}
              onChange={(e) => setStudentId(e.target.value)}
            />
          </div>

          <div className="tabs">
            {TABS.map((t) => (
              <button
                key={t.id}
                type="button"
                className={`tab ${tab === t.id ? "active" : ""}`}
                onClick={() => {
                  setTab(t.id);
                  setFile(null);
                  setError(null);
                }}
              >
                {t.label}
              </button>
            ))}
          </div>
          <p className="text-muted" style={{ marginTop: -10 }}>
            {TABS.find((t) => t.id === tab)?.hint}
          </p>

          {tab === "typed" ? (
            <>
              <div className="field">
                <label className="field-label">Answer text</label>
                <textarea
                  className="textarea"
                  style={{ fontFamily: "var(--font-body)", minHeight: 180 }}
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  placeholder="Paste or type the student's answer…"
                />
              </div>
              <button className="btn btn-accent" onClick={handleUploadTyped} disabled={busy}>
                {busy && <Spinner />} {busy ? "Submitting…" : "Submit answer"}
              </button>
            </>
          ) : (
            <>
              <label className="dropzone" htmlFor="file-input">
                <input
                  id="file-input"
                  type="file"
                  accept={tab === "pdf" ? "application/pdf" : "image/*"}
                  onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                />
                {file ? (
                  <div className="dropzone-filename">{file.name}</div>
                ) : (
                  <div>Click to choose a {tab === "pdf" ? "PDF" : "image"} file, or drag one here.</div>
                )}
              </label>
              <div style={{ marginTop: 14 }}>
                <button className="btn btn-accent" onClick={handleUploadFile} disabled={busy || !file}>
                  {busy && <Spinner />} {busy ? "Uploading & extracting…" : "Upload & extract text"}
                </button>
                {busy && (
                  <div className="field-hint" style={{ marginTop: 6 }}>
                    Scanned/handwritten pages are run through OCR — this can take a few seconds per page.
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      ) : (
        <div className="card">
          <div className="card-header">
            <h2>Review recognized text</h2>
            {extracted && (
              <span className={`badge ${extracted.recognition_confidence >= 0.75 ? "badge-supported" : "badge-not_supported"}`}>
                Recognition confidence {extracted.recognition_confidence.toFixed(2)}
              </span>
            )}
          </div>

          {tab === "handwritten" && (
            <div className="alert alert-warning" style={{ marginBottom: 14 }}>
              Handwritten submissions are always routed to faculty review after grading, regardless
              of the confidence score above — please check this text carefully before continuing.
            </div>
          )}

          <div style={{ display: "grid", gridTemplateColumns: imagePreviewUrl ? "1fr 1fr" : "1fr", gap: 18 }}>
            {imagePreviewUrl && (
              <div>
                <div className="section-label" style={{ marginBottom: 6 }}>
                  Original image
                </div>
                <img
                  src={imagePreviewUrl}
                  alt="Uploaded answer"
                  style={{ width: "100%", border: "1px solid var(--rule)", borderRadius: "var(--radius)" }}
                />
              </div>
            )}
            <div>
              <div className="section-label" style={{ marginBottom: 6 }}>
                Extracted text {extracted?.manually_corrected && "(manually corrected)"}
              </div>
              <textarea
                className="textarea"
                style={{ minHeight: imagePreviewUrl ? 300 : 180 }}
                value={editedText}
                onChange={(e) => setEditedText(e.target.value)}
              />
              {extracted && editedText !== extracted.text && (
                <button className="btn btn-secondary btn-sm" style={{ marginTop: 8 }} onClick={handleSaveCorrection} disabled={busy}>
                  Save correction
                </button>
              )}
            </div>
          </div>

          <div style={{ marginTop: 18, display: "flex", gap: 10 }}>
            <button className="btn btn-accent" onClick={handleGrade} disabled={busy || !editedText.trim()}>
              {busy && <Spinner />} {busy ? "Grading…" : "Grade this answer →"}
            </button>
            <button className="btn btn-ghost" onClick={resetToInput} type="button">
              Start over
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
