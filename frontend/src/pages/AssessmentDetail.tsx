import { FormEvent, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type { AssessmentDetail as AssessmentDetailType, AssessmentReport } from "../api/types";
import { ErrorNotice, Spinner } from "../components/Shared";

export default function AssessmentDetail() {
  const { assessmentId } = useParams();
  const id = Number(assessmentId);
  const [assessment, setAssessment] = useState<AssessmentDetailType | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [addingQuestion, setAddingQuestion] = useState(false);
  const [newQuestionText, setNewQuestionText] = useState("");
  const [newMaxMarks, setNewMaxMarks] = useState(10);

  const [studentId, setStudentId] = useState("");
  const [report, setReport] = useState<AssessmentReport | null>(null);
  const [reportError, setReportError] = useState<string | null>(null);
  const [reportLoading, setReportLoading] = useState(false);

  function refresh() {
    api
      .getAssessment(id)
      .then(setAssessment)
      .catch((e) => setError(e instanceof ApiError ? e.message : String(e)));
  }

  useEffect(refresh, [id]);

  async function handleAddQuestion(e: FormEvent) {
    e.preventDefault();
    if (!newQuestionText.trim() || newMaxMarks <= 0) return;
    await api.createQuestion(id, {
      question_text: newQuestionText.trim(),
      max_marks: newMaxMarks,
      criteria: [],
    });
    setNewQuestionText("");
    setNewMaxMarks(10);
    setAddingQuestion(false);
    refresh();
  }

  async function loadReport() {
    setReportLoading(true);
    setReportError(null);
    try {
      const r = await api.getReport(id, studentId.trim() || undefined);
      setReport(r);
    } catch (e) {
      setReportError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setReportLoading(false);
    }
  }

  if (error) return <ErrorNotice message={error} />;
  if (!assessment)
    return (
      <div className="empty-state">
        <Spinner /> Loading…
      </div>
    );

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="page-eyebrow">{assessment.subject ?? "Assessment"}</div>
          <h1>{assessment.name}</h1>
          <p className="page-subtitle">
            {assessment.questions.length} question{assessment.questions.length === 1 ? "" : "s"} ·
            created {new Date(assessment.created_at).toLocaleDateString()}
          </p>
        </div>
      </div>

      <div className="card">
        <div className="card-header">
          <h2>Questions</h2>
          <button className="btn btn-secondary btn-sm" onClick={() => setAddingQuestion((v) => !v)}>
            {addingQuestion ? "Cancel" : "+ Add question"}
          </button>
        </div>

        {addingQuestion && (
          <form onSubmit={handleAddQuestion} className="card" style={{ background: "var(--surface-alt)", marginBottom: 16 }}>
            <div className="field">
              <label className="field-label">Question text</label>
              <textarea
                className="textarea"
                style={{ fontFamily: "var(--font-body)" }}
                value={newQuestionText}
                onChange={(e) => setNewQuestionText(e.target.value)}
              />
            </div>
            <div className="field" style={{ maxWidth: 180 }}>
              <label className="field-label">Maximum marks</label>
              <input
                type="number"
                min={0.5}
                step={0.5}
                className="input"
                value={newMaxMarks}
                onChange={(e) => setNewMaxMarks(Number(e.target.value))}
              />
            </div>
            <button type="submit" className="btn btn-accent btn-sm">
              Add question
            </button>
          </form>
        )}

        {assessment.questions.length === 0 && !addingQuestion ? (
          <div className="empty-state">No questions yet.</div>
        ) : (
          assessment.questions.map((q) => {
            const sum = q.criteria.reduce((acc, c) => acc + c.marks, 0);
            const rubricComplete = q.criteria.length > 0 && Math.abs(sum - q.max_marks) < 0.01;
            return (
              <div className="list-row" key={q.id}>
                <div>
                  <div className="list-row-title">{q.question_text}</div>
                  <div className="list-row-meta">
                    {q.max_marks} marks total ·{" "}
                    {q.criteria.length === 0
                      ? "no rubric yet"
                      : rubricComplete
                      ? `${q.criteria.length} criteria, rubric complete`
                      : `${q.criteria.length} criteria, sums to ${sum.toFixed(2)} (needs ${q.max_marks})`}
                  </div>
                </div>
                <div style={{ display: "flex", gap: 8 }}>
                  <Link to={`/questions/${q.id}/rubric`} className="btn btn-secondary btn-sm">
                    {rubricComplete ? "Edit rubric" : "Build rubric"}
                  </Link>
                  <Link
                    to={`/questions/${q.id}/upload`}
                    className={`btn btn-sm ${rubricComplete ? "btn-accent" : "btn-secondary"}`}
                    aria-disabled={!rubricComplete}
                    onClick={(e) => !rubricComplete && e.preventDefault()}
                    title={rubricComplete ? "Submit an answer to grade" : "Complete the rubric first"}
                  >
                    Submit answer
                  </Link>
                </div>
              </div>
            );
          })
        )}
      </div>

      <div className="card">
        <div className="card-header">
          <h2>Report</h2>
        </div>
        <p className="text-muted">
          Leave the student field blank for an assessment-wide summary, or enter a student
          identifier to pull their individual report across all questions.
        </p>
        <div className="input-row" style={{ alignItems: "flex-end" }}>
          <div className="field mb-0" style={{ maxWidth: 260 }}>
            <label className="field-label">Student identifier (optional)</label>
            <input
              className="input"
              placeholder="e.g. student-042"
              value={studentId}
              onChange={(e) => setStudentId(e.target.value)}
            />
          </div>
          <button className="btn btn-secondary" onClick={loadReport} disabled={reportLoading}>
            {reportLoading ? "Loading…" : "View report"}
          </button>
          <a className="btn btn-secondary" href={api.reportPdfUrl(id, studentId.trim() || undefined)} target="_blank" rel="noreferrer">
            Download PDF
          </a>
        </div>

        {reportError && <ErrorNotice message={reportError} />}

        {report && (
          <div style={{ marginTop: 16 }}>
            <div className="stat-grid">
              <div className="stat-card">
                <div className="stat-value">
                  {report.total_final_marks}
                  <span className="unit">/{report.total_max_marks}</span>
                </div>
                <div className="stat-label">Final total</div>
              </div>
              <div className="stat-card">
                <div className="stat-value">
                  {report.percentage}
                  <span className="unit">%</span>
                </div>
                <div className="stat-label">Percentage</div>
              </div>
              <div className="stat-card">
                <div className="stat-value">{report.flagged_for_review.length}</div>
                <div className="stat-label">Flagged items</div>
              </div>
            </div>

            <table className="table">
              <thead>
                <tr>
                  <th>Question</th>
                  <th>AI awarded</th>
                  <th>Final</th>
                  <th>Review?</th>
                </tr>
              </thead>
              <tbody>
                {report.questions.map((q) => (
                  <tr key={q.question_id}>
                    <td>{q.question_text}</td>
                    <td className="mono">
                      {q.awarded_marks}/{q.total_marks}
                    </td>
                    <td className="mono">
                      {q.final_marks}/{q.total_marks}
                    </td>
                    <td>{q.review_required ? <span className="text-danger">Yes</span> : "No"}</td>
                  </tr>
                ))}
              </tbody>
            </table>

            {report.flagged_for_review.length > 0 && (
              <div className="alert alert-warning" style={{ marginTop: 12 }}>
                <div>
                  <strong>Flagged for review:</strong>
                  <ul>
                    {report.flagged_for_review.map((f, i) => (
                      <li key={i}>{f}</li>
                    ))}
                  </ul>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
