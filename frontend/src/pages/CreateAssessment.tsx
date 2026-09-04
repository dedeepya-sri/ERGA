import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, ApiError } from "../api/client";
import { ErrorNotice } from "../components/Shared";

export default function CreateAssessment() {
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [subject, setSubject] = useState("");
  const [questionText, setQuestionText] = useState("");
  const [maxMarks, setMaxMarks] = useState<number>(10);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!name.trim() || !questionText.trim() || maxMarks <= 0) {
      setError("Assessment name, question text, and a positive maximum marks are all required.");
      return;
    }
    setSubmitting(true);
    try {
      const assessment = await api.createAssessment({ name: name.trim(), subject: subject.trim() || undefined });
      // Create the question with an empty rubric — the Rubric Builder page
      // is where criteria actually get added and validated against max_marks.
      const question = await api.createQuestion(assessment.id, {
        question_text: questionText.trim(),
        max_marks: maxMarks,
        criteria: [],
      });
      navigate(`/questions/${question.id}/rubric`, { state: { assessmentId: assessment.id } });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="page-eyebrow">New assessment</div>
          <h1>Create assessment</h1>
          <p className="page-subtitle">
            Start with the assessment name and the first question. You'll build its rubric on the
            next screen — the rubric is authoritative, so nothing gets graded until it's in place.
          </p>
        </div>
      </div>

      {error && <ErrorNotice message={error} />}

      <form className="card" onSubmit={handleSubmit}>
        <div className="input-row">
          <div className="field">
            <label className="field-label" htmlFor="name">
              Assessment name
            </label>
            <input
              id="name"
              className="input"
              placeholder="e.g. Midterm — Data Structures"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <div className="field">
            <label className="field-label" htmlFor="subject">
              Subject
            </label>
            <input
              id="subject"
              className="input"
              placeholder="e.g. Computer Science"
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
            />
          </div>
        </div>

        <div className="field">
          <label className="field-label" htmlFor="question">
            Question
          </label>
          <textarea
            id="question"
            className="textarea"
            style={{ fontFamily: "var(--font-body)" }}
            placeholder="e.g. Explain the difference between a stack and a queue, with one real-world example of each."
            value={questionText}
            onChange={(e) => setQuestionText(e.target.value)}
          />
        </div>

        <div className="field" style={{ maxWidth: 200 }}>
          <label className="field-label" htmlFor="max-marks">
            Maximum marks
          </label>
          <input
            id="max-marks"
            type="number"
            min={0.5}
            step={0.5}
            className="input"
            value={maxMarks}
            onChange={(e) => setMaxMarks(Number(e.target.value))}
          />
        </div>

        <button type="submit" className="btn btn-accent" disabled={submitting}>
          {submitting ? "Creating…" : "Continue to rubric builder →"}
        </button>
      </form>
    </div>
  );
}
