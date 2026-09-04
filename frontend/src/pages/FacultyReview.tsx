import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type { GradingResult } from "../api/types";
import { ErrorNotice, Spinner, StatusBadge } from "../components/Shared";

export default function FacultyReview() {
  const { submissionId } = useParams();
  const id = Number(submissionId);
  const [result, setResult] = useState<GradingResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reviewer, setReviewer] = useState("");

  function refresh() {
    api
      .getResult(id)
      .then(setResult)
      .catch((e) => setError(e instanceof ApiError ? e.message : String(e)));
  }

  useEffect(refresh, [id]);

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
          <div className="page-eyebrow">
            <Link to={`/submissions/${id}/result`}>← Back to grading result</Link>
          </div>
          <h1>Faculty review</h1>
          <p className="page-subtitle">
            Accept the AI's assessment as-is, or override any criterion below. Every override is
            saved with a reason and timestamp — the AI's original number is never overwritten,
            only superseded.
          </p>
        </div>
        <div style={{ textAlign: "right" }}>
          <div className="stat-value">
            {result.final_marks}
            <span className="unit">/{result.total_marks}</span>
          </div>
          <div className="stat-label">Current final score</div>
        </div>
      </div>

      <div className="field" style={{ maxWidth: 280, marginBottom: 24 }}>
        <label className="field-label">Reviewer name (attached to any overrides you save)</label>
        <input className="input" value={reviewer} onChange={(e) => setReviewer(e.target.value)} placeholder="e.g. Prof. Rao" />
      </div>

      {result.criteria.map((c, idx) => (
        <CriterionReviewRow
          key={c.id}
          index={idx}
          criterion={c}
          reviewer={reviewer}
          onChanged={refresh}
        />
      ))}
    </div>
  );
}

function CriterionReviewRow({
  index,
  criterion,
  reviewer,
  onChanged,
}: {
  index: number;
  criterion: GradingResult["criteria"][number];
  reviewer: string;
  onChanged: () => void;
}) {
  const [facultyMarks, setFacultyMarks] = useState(criterion.review?.faculty_marks ?? criterion.marks);
  const [reason, setReason] = useState(criterion.review?.reason ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    setBusy(true);
    setError(null);
    try {
      await api.submitReview({
        criterion_result_id: criterion.id,
        faculty_marks: facultyMarks,
        reason: reason.trim() || undefined,
        reviewer: reviewer.trim() || undefined,
      });
      onChanged();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function clear() {
    setBusy(true);
    setError(null);
    try {
      await api.clearReview(criterion.id);
      setFacultyMarks(criterion.marks);
      setReason("");
      onChanged();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const flagged = criterion.grading_confidence < 0.6;

  return (
    <div className={`criterion-card ${flagged ? "flagged" : ""}`}>
      <div className="criterion-top">
        <div>
          <div className="criterion-label">Criterion C{index + 1}</div>
          <h3 style={{ marginBottom: 4 }}>{criterion.description}</h3>
          <StatusBadge status={criterion.status} />
          {flagged && (
            <span className="badge badge-not_supported" style={{ marginLeft: 6 }}>
              Low confidence ({criterion.grading_confidence.toFixed(2)})
            </span>
          )}
        </div>
        <div className="criterion-marks">
          AI: {criterion.marks}
          <span className="max"> / {criterion.max_marks}</span>
        </div>
      </div>

      {criterion.evidence[0] && (
        <div className="evidence-block">“{criterion.evidence[0].text}”</div>
      )}
      {criterion.missing_concepts.length > 0 && (
        <div className="missing-terms">
          Missing terms: <span className="mono">{criterion.missing_concepts.join(", ")}</span>
        </div>
      )}

      <div className="review-box">
        {error && <ErrorNotice message={error} />}
        <div className="input-row" style={{ alignItems: "flex-end" }}>
          <div className="field mb-0" style={{ maxWidth: 140 }}>
            <label className="field-label">Faculty marks</label>
            <input
              type="number"
              min={0}
              max={criterion.max_marks}
              step={0.5}
              className="input mono"
              value={facultyMarks}
              onChange={(e) => setFacultyMarks(Number(e.target.value))}
            />
          </div>
          <div className="field mb-0" style={{ flex: 2 }}>
            <label className="field-label">Reason for override (optional but recommended)</label>
            <input
              className="input"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="e.g. Diagram on paper covered this point, not captured in extracted text"
            />
          </div>
          <button className="btn btn-accent" onClick={save} disabled={busy}>
            {busy ? "Saving…" : criterion.review ? "Update override" : "Save override"}
          </button>
          {criterion.review && (
            <button className="btn btn-ghost" onClick={clear} disabled={busy} type="button">
              Revert to AI
            </button>
          )}
        </div>
        {criterion.review && (
          <div className="evidence-meta" style={{ marginTop: 8 }}>
            Last saved by {criterion.review.reviewer || "unattributed"} on{" "}
            {new Date(criterion.review.timestamp).toLocaleString()}
          </div>
        )}
      </div>
    </div>
  );
}
