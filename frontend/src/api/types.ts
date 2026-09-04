export type InputType = "typed" | "pdf" | "scan" | "handwritten";
export type CriterionStatus = "supported" | "partially_supported" | "not_supported";

export interface RubricCriterion {
  id: number;
  description: string;
  marks: number;
  reference_concepts: string[];
  order_index: number;
}

export interface RubricCriterionDraft {
  description: string;
  marks: number;
  reference_concepts: string[];
}

export interface Question {
  id: number;
  assessment_id: number;
  question_text: string;
  max_marks: number;
  criteria: RubricCriterion[];
}

export interface Assessment {
  id: number;
  name: string;
  subject: string | null;
  created_at: string;
}

export interface AssessmentDetail extends Assessment {
  questions: Question[];
}

export interface RubricValidation {
  valid: boolean;
  sum_marks: number;
  max_marks: number;
  difference: number;
  message: string;
}

export interface Submission {
  id: number;
  question_id: number;
  student_identifier: string | null;
  input_type: InputType;
  file_path: string | null;
  created_at: string;
}

export interface ExtractedLine {
  page: number;
  bbox: { left: number; top: number; width: number; height: number } | null;
  confidence: number;
}

export interface ExtractedAnswer {
  id: number;
  submission_id: number;
  text: string;
  recognition_confidence: number;
  manually_corrected: boolean;
  engine: string | null;
  source_detail: { lines?: ExtractedLine[]; page_count?: number };
}

export interface Evidence {
  text: string;
  similarity: number;
  segment_index: number | null;
  page: number | null;
  bbox: Record<string, number> | null;
}

export interface Review {
  ai_marks: number;
  faculty_marks: number;
  reason: string | null;
  reviewer: string | null;
  timestamp: string;
}

export interface CriterionResult {
  id: number;
  criterion_id: number;
  description: string;
  status: CriterionStatus;
  marks: number;
  max_marks: number;
  composite_score: number;
  grading_confidence: number;
  missing_concepts: string[];
  evidence: Evidence[];
  review: Review | null;
  engine_info: Record<string, unknown>;
}

export interface GradingResult {
  submission_id: number;
  question_id: number;
  question_text: string;
  total_marks: number;
  awarded_marks: number;
  final_marks: number;
  recognition_confidence: number;
  grading_confidence: number;
  review_required: boolean;
  review_reasons: string[];
  criteria: CriterionResult[];
}

export interface QuestionReportEntry {
  question_id: number;
  question_text: string;
  total_marks: number;
  awarded_marks: number;
  final_marks: number;
  review_required: boolean;
  criteria_requiring_review: string[];
}

export interface AssessmentReport {
  assessment_id: number;
  assessment_name: string;
  student_identifier: string | null;
  total_max_marks: number;
  total_awarded_marks: number;
  total_final_marks: number;
  percentage: number;
  questions: QuestionReportEntry[];
  flagged_for_review: string[];
}

export interface DashboardStats {
  total_submissions: number;
  graded_submissions: number;
  average_score_pct: number | null;
  questions_graded: number;
  reviews_required: number;
  reviews_completed: number;
  average_recognition_confidence: number | null;
  average_grading_confidence: number | null;
}

// Thresholds used by the confidence-strip visualization. Mirrors
// backend/config/model_config.yaml — if you change the thresholds there,
// update these too (a future improvement would be to serve them from
// GET /api/health so the UI never drifts from the config file).
export const NLI_THRESHOLDS = { partialMin: 0.32, supportedMin: 0.62 };
