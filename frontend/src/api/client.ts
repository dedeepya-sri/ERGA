import type {
  Assessment,
  AssessmentDetail,
  AssessmentReport,
  DashboardStats,
  ExtractedAnswer,
  GradingResult,
  Question,
  RubricCriterionDraft,
  RubricValidation,
  Submission,
} from "./types";

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers:
      options.body && !(options.body instanceof FormData)
        ? { "Content-Type": "application/json", ...options.headers }
        : options.headers,
    ...options,
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = body.detail ?? JSON.stringify(body);
    } catch {
      // response wasn't JSON — fall back to statusText
    }
    throw new ApiError(response.status, detail);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const api = {
  // ---- health ----
  health: () => request<{ status: string; embedding_engine: string; nli_engine: string; ocr_engine: string; scoring_mode: string }>("/api/health"),

  // ---- assessments ----
  listAssessments: () => request<Assessment[]>("/api/assessments"),
  getAssessment: (id: number) => request<AssessmentDetail>(`/api/assessments/${id}`),
  createAssessment: (data: { name: string; subject?: string }) =>
    request<Assessment>("/api/assessments", { method: "POST", body: JSON.stringify(data) }),
  deleteAssessment: (id: number) => request<void>(`/api/assessments/${id}`, { method: "DELETE" }),

  // ---- questions / rubric ----
  createQuestion: (
    assessmentId: number,
    data: { question_text: string; max_marks: number; criteria: RubricCriterionDraft[] }
  ) =>
    request<Question>(`/api/assessments/${assessmentId}/questions`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  getQuestion: (id: number) => request<Question>(`/api/questions/${id}`),
  replaceCriteria: (questionId: number, criteria: RubricCriterionDraft[]) =>
    request<Question>(`/api/questions/${questionId}/criteria`, {
      method: "PUT",
      body: JSON.stringify(criteria),
    }),
  validateRubric: (questionId: number, criteria: RubricCriterionDraft[]) =>
    request<RubricValidation>(`/api/questions/${questionId}/rubric/validate`, {
      method: "POST",
      body: JSON.stringify(criteria),
    }),

  // ---- submissions ----
  createTypedSubmission: (data: { question_id: number; text: string; student_identifier?: string }) => {
    const form = new FormData();
    form.append("question_id", String(data.question_id));
    form.append("input_type", "typed");
    form.append("text", data.text);
    if (data.student_identifier) form.append("student_identifier", data.student_identifier);
    return request<Submission>("/api/submissions", { method: "POST", body: form });
  },
  createFileSubmission: (data: {
    question_id: number;
    input_type: "pdf" | "scan" | "handwritten";
    file: File;
    student_identifier?: string;
  }) => {
    const form = new FormData();
    form.append("question_id", String(data.question_id));
    form.append("input_type", data.input_type);
    form.append("file", data.file);
    if (data.student_identifier) form.append("student_identifier", data.student_identifier);
    return request<Submission>("/api/submissions", { method: "POST", body: form });
  },
  extractSubmission: (id: number) =>
    request<ExtractedAnswer>(`/api/submissions/${id}/extract`, { method: "POST" }),
  getExtractedText: (id: number) =>
    request<ExtractedAnswer>(`/api/submissions/${id}/extracted-text`),
  correctExtractedText: (id: number, text: string) =>
    request<ExtractedAnswer>(`/api/submissions/${id}/extracted-text`, {
      method: "PUT",
      body: JSON.stringify({ text }),
    }),
  gradeSubmission: (id: number) =>
    request<GradingResult>(`/api/submissions/${id}/grade`, { method: "POST" }),
  getResult: (id: number) => request<GradingResult>(`/api/submissions/${id}/result`),
  getSubmission: (id: number) => request<Submission>(`/api/submissions/${id}`),
  deleteSubmission: (id: number) => request<void>(`/api/submissions/${id}`, { method: "DELETE" }),

  // ---- reviews ----
  submitReview: (data: {
    criterion_result_id: number;
    faculty_marks: number;
    reason?: string;
    reviewer?: string;
  }) => request("/api/reviews", { method: "POST", body: JSON.stringify(data) }),
  clearReview: (criterionResultId: number) =>
    request<void>(`/api/reviews/${criterionResultId}`, { method: "DELETE" }),

  // ---- reports / dashboard ----
  getReport: (assessmentId: number, studentIdentifier?: string) =>
    request<AssessmentReport>(
      `/api/reports/${assessmentId}${studentIdentifier ? `?student_identifier=${encodeURIComponent(studentIdentifier)}` : ""}`
    ),
  reportPdfUrl: (assessmentId: number, studentIdentifier?: string) =>
    `${API_BASE}/api/reports/${assessmentId}/pdf${studentIdentifier ? `?student_identifier=${encodeURIComponent(studentIdentifier)}` : ""}`,
  dashboardStats: () => request<DashboardStats>("/api/dashboard/stats"),
};

export { ApiError };
