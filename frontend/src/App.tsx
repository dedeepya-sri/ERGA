import { BrowserRouter, Route, Routes } from "react-router-dom";
import { NavBar } from "./components/Shared";
import Dashboard from "./pages/Dashboard";
import CreateAssessment from "./pages/CreateAssessment";
import AssessmentDetail from "./pages/AssessmentDetail";
import RubricBuilder from "./pages/RubricBuilder";
import AnswerUpload from "./pages/AnswerUpload";
import GradingResult from "./pages/GradingResult";
import FacultyReview from "./pages/FacultyReview";

export default function App() {
  return (
    <BrowserRouter>
      <div className="app-shell">
        <NavBar />
        <main className="app-main">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/assessments/new" element={<CreateAssessment />} />
            <Route path="/assessments/:assessmentId" element={<AssessmentDetail />} />
            <Route path="/questions/:questionId/rubric" element={<RubricBuilder />} />
            <Route path="/questions/:questionId/upload" element={<AnswerUpload />} />
            <Route path="/submissions/:submissionId/result" element={<GradingResult />} />
            <Route path="/submissions/:submissionId/review" element={<FacultyReview />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}
