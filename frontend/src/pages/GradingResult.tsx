import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type { GradingResult as GradingResultType } from "../api/types";
import { ConfidenceStrip, ErrorNotice, Spinner, StatusBadge } from "../components/Shared";

export default function GradingResult() {
  const { submissionId } = useParams();
  const id = Number(submissionId);
  const [result, setResult] = useState<GradingResultType | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .getResult(id)
      .then(setResult)
      .catch((e) => setError(e instanceof ApiError ? e.message : String(e)));
  }, [id]);

  if (error) return <ErrorNotice message={error} />;
  if (!result)
    return (
      <div className="empty-state">
        <Spinner /> Loading…
      </div>
    );

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="page-eyebrow">Grading result</div>
          <h1>{result.question_text}</h1>
          <p className="page-subtitle">
            Submission #{result.submission_id} · engine:{" "}
            {result.criteria[0]?.engine_info?.embedder as string}
            {" + "}
            {result.criteria[0]?.engine_info?.nli as string}
          </p>
        </div>
        <div style={{ textAlign: "right" }}>
          <div className="stat-value">
            {result.final_marks}
            <span className="unit">/{result.total_marks}</span>
          </div>
          <div className="stat-label">
            {result.final_marks !== result.awarded_marks
              ? `AI recommended ${result.awarded_marks}`
              : "AI recommendation"}
          </div>
        </div>
      </div>

      {result.review_required && (
        <div className="alert alert-warning" style={{ marginBottom: 20 }}>
          <div>
            <strong>⚠ Faculty review recommended</strong>
            <ul>
              {result.review_reasons.map((r, i) => (
                <li key={i}>{r}</li>
              ))}
            </ul>
            <Link to={`/submissions/${result.submission_id}/review`} className="btn btn-accent btn-sm" style={{ marginTop: 8 }}>
              Go to faculty review →
            </Link>
          </div>
        </div>
      )}

      <div className="stat-grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))" }}>
        <div className="stat-card">
          <div className="stat-value">{result.recognition_confidence.toFixed(2)}</div>
          <div className="stat-label">Recognition confidence</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{result.grading_confidence.toFixed(2)}</div>
          <div className="stat-label">Grading confidence (weakest criterion)</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{result.criteria.length}</div>
          <div className="stat-label">Criteria assessed</div>
        </div>
      </div>

      <h2>Criterion breakdown</h2>
      {result.criteria.map((c, idx) => (
        <div className={`criterion-card ${c.grading_confidence < 0.6 ? "flagged" : ""}`} key={c.id}>
          <div className="criterion-top">
            <div>
              <div className="criterion-label">Criterion C{idx + 1}</div>
              <h3 style={{ marginBottom: 4 }}>{c.description}</h3>
              <StatusBadge status={c.status} />
              {c.review && (
                <span className="badge badge-neutral" style={{ marginLeft: 6 }}>
                  Faculty override applied
                </span>
              )}
            </div>
            <div className="criterion-marks">
              {c.review ? (
                <>
                  <span style={{ textDecoration: "line-through", color: "var(--ink-faint)", fontSize: "0.75em" }}>
                    {c.marks}
                  </span>{" "}
                  {c.review.faculty_marks}
                  <span className="max"> / {c.max_marks}</span>
                </>
              ) : (
                <>
                  {c.marks}
                  <span className="max"> / {c.max_marks}</span>
                </>
              )}
            </div>
          </div>

          <ConfidenceStrip score={c.composite_score} label="Composite" />

          {c.evidence.length > 0 ? (
            c.evidence.map((e, i) => (
              <div className="evidence-block" key={i}>
                “{e.text}”
                <div className="evidence-meta">
                  similarity {e.similarity.toFixed(2)}
                  {e.page !== null && ` · page ${e.page}`}
                </div>
              </div>
            ))
          ) : (
            <div className="evidence-block text-faint">No matching evidence found in the answer.</div>
          )}

          {c.missing_concepts.length > 0 && (
            <div className="missing-terms">
              Missing terms: <span className="mono">{c.missing_concepts.join(", ")}</span>
            </div>
          )}

          <div className="evidence-meta" style={{ marginTop: 10 }}>
            Grading confidence {c.grading_confidence.toFixed(2)}
            {c.review && (
              <> · faculty note: {c.review.reason || "—"} ({c.review.reviewer || "unattributed"})</>
            )}
          </div>
        </div>
      ))}

      <div style={{ marginTop: 20, display: "flex", gap: 10 }}>
        <Link to={`/submissions/${result.submission_id}/review`} className="btn btn-accent">
          Open faculty review →
        </Link>
      </div>
    </div>
  );
}
