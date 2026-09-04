import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type { Question, RubricCriterionDraft } from "../api/types";
import { ErrorNotice, Spinner } from "../components/Shared";

interface DraftRow extends RubricCriterionDraft {
  referenceConceptsText: string;
}

function toDraftRow(c: RubricCriterionDraft): DraftRow {
  return { ...c, referenceConceptsText: c.reference_concepts.join(", ") };
}

export default function RubricBuilder() {
  const { questionId } = useParams();
  const id = Number(questionId);
  const navigate = useNavigate();

  const [question, setQuestion] = useState<Question | null>(null);
  const [rows, setRows] = useState<DraftRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.getQuestion(id).then((q) => {
      setQuestion(q);
      setRows(
        q.criteria.length > 0
          ? q.criteria.map((c) => toDraftRow(c))
          : [toDraftRow({ description: "", marks: 0, reference_concepts: [] })]
      );
    });
  }, [id]);

  const sum = useMemo(() => rows.reduce((acc, r) => acc + (Number.isFinite(r.marks) ? r.marks : 0), 0), [rows]);
  const diff = question ? Math.round((sum - question.max_marks) * 100) / 100 : 0;
  const valid = question ? Math.abs(diff) < 0.01 : false;

  function updateRow(idx: number, patch: Partial<DraftRow>) {
    setRows((prev) => prev.map((r, i) => (i === idx ? { ...r, ...patch } : r)));
  }

  function addRow() {
    setRows((prev) => [...prev, toDraftRow({ description: "", marks: 0, reference_concepts: [] })]);
  }

  function removeRow(idx: number) {
    setRows((prev) => prev.filter((_, i) => i !== idx));
  }

  async function handleSave() {
    setError(null);
    if (rows.some((r) => !r.description.trim())) {
      setError("Every criterion needs a description.");
      return;
    }
    if (!valid) {
      setError("Criteria marks must sum exactly to the question's maximum marks before saving.");
      return;
    }
    setSaving(true);
    try {
      const payload: RubricCriterionDraft[] = rows.map((r) => ({
        description: r.description.trim(),
        marks: r.marks,
        reference_concepts: r.referenceConceptsText
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
      }));
      const updated = await api.replaceCriteria(id, payload);
      navigate(`/questions/${updated.id}/upload`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setSaving(false);
    }
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
          <h1>Rubric builder</h1>
          <p className="page-subtitle">
            “{question.question_text}” — worth <strong className="mono">{question.max_marks}</strong> marks. The
            rubric is authoritative: the grading engine never awards marks the rubric doesn't define.
          </p>
        </div>
      </div>

      {error && <ErrorNotice message={error} />}

      <div className="card">
        <div className="card-header">
          <h2>Criteria</h2>
          <span className="section-label">{rows.length} criteria</span>
        </div>

        <div className="rubric-row" style={{ marginBottom: 4 }}>
          <span className="section-label">Description</span>
          <span className="section-label">Marks</span>
          <span className="section-label">Reference concepts (optional, comma-separated)</span>
          <span />
        </div>

        {rows.map((row, idx) => (
          <div className="rubric-row" key={idx}>
            <input
              className="input"
              placeholder={`Criterion C${idx + 1} — what must the answer show?`}
              value={row.description}
              onChange={(e) => updateRow(idx, { description: e.target.value })}
            />
            <input
              className="input mono"
              type="number"
              min={0}
              step={0.5}
              value={row.marks}
              onChange={(e) => updateRow(idx, { marks: Number(e.target.value) })}
            />
            <input
              className="input"
              placeholder="e.g. labelled data, training examples"
              value={row.referenceConceptsText}
              onChange={(e) => updateRow(idx, { referenceConceptsText: e.target.value })}
            />
            <button
              className="btn btn-ghost btn-sm"
              onClick={() => removeRow(idx)}
              disabled={rows.length === 1}
              title="Remove criterion"
              type="button"
            >
              ✕
            </button>
          </div>
        ))}

        <button className="btn btn-secondary btn-sm" onClick={addRow} type="button">
          + Add criterion
        </button>

        <div className={`rubric-sum-check ${valid ? "rubric-sum-ok" : "rubric-sum-bad"}`}>
          <span>
            Sum: {sum.toFixed(2)} / {question.max_marks.toFixed(2)}
          </span>
          <span>
            {valid
              ? "✓ Matches maximum marks"
              : `${diff > 0 ? "Over" : "Under"} by ${Math.abs(diff).toFixed(2)}`}
          </span>
        </div>

        <div style={{ marginTop: 20, display: "flex", gap: 10 }}>
          <button className="btn btn-accent" onClick={handleSave} disabled={saving || !valid}>
            {saving ? "Saving…" : "Save rubric & continue →"}
          </button>
        </div>
      </div>
    </div>
  );
}
