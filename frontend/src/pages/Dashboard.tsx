import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type { Assessment, DashboardStats } from "../api/types";
import { ErrorNotice, Spinner } from "../components/Shared";

export default function Dashboard() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [assessments, setAssessments] = useState<Assessment[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.dashboardStats(), api.listAssessments()])
      .then(([s, a]) => {
        setStats(s);
        setAssessments(a);
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : String(e)));
  }, []);

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="page-eyebrow">Overview</div>
          <h1>Dashboard</h1>
          <p className="page-subtitle">
            A running summary of everything graded through this instance — how much has been
            processed, how confident the engine was, and how much still needs a human look.
          </p>
        </div>
        <Link to="/assessments/new" className="btn btn-accent">
          + Create assessment
        </Link>
      </div>

      {error && <ErrorNotice message={error} />}

      {!stats || !assessments ? (
        <div className="empty-state">
          <Spinner /> Loading…
        </div>
      ) : (
        <>
          <div className="stat-grid">
            <StatCard label="Total submissions" value={stats.total_submissions} />
            <StatCard label="Graded submissions" value={stats.graded_submissions} />
            <StatCard
              label="Average score"
              value={stats.average_score_pct === null ? "—" : stats.average_score_pct.toFixed(1)}
              unit={stats.average_score_pct === null ? undefined : "%"}
            />
            <StatCard label="Questions graded" value={stats.questions_graded} />
            <StatCard
              label="Reviews required"
              value={stats.reviews_required}
              highlight={stats.reviews_required > 0}
            />
            <StatCard label="Reviews completed" value={stats.reviews_completed} />
            <StatCard
              label="Avg. recognition confidence"
              value={stats.average_recognition_confidence === null ? "—" : stats.average_recognition_confidence.toFixed(2)}
            />
            <StatCard
              label="Avg. grading confidence"
              value={stats.average_grading_confidence === null ? "—" : stats.average_grading_confidence.toFixed(2)}
            />
          </div>

          <div className="card">
            <div className="card-header">
              <h2>Assessments</h2>
            </div>
            {assessments.length === 0 ? (
              <div className="empty-state">
                No assessments yet.{" "}
                <Link to="/assessments/new">Create your first one</Link>.
              </div>
            ) : (
              assessments.map((a) => (
                <div className="list-row" key={a.id}>
                  <div>
                    <div className="list-row-title">
                      <Link to={`/assessments/${a.id}`}>{a.name}</Link>
                    </div>
                    <div className="list-row-meta">
                      {a.subject ?? "No subject"} · created{" "}
                      {new Date(a.created_at).toLocaleDateString()}
                    </div>
                  </div>
                  <Link to={`/assessments/${a.id}`} className="btn btn-secondary btn-sm">
                    Open
                  </Link>
                </div>
              ))
            )}
          </div>
        </>
      )}
    </div>
  );
}

function StatCard({
  label,
  value,
  unit,
  highlight,
}: {
  label: string;
  value: number | string;
  unit?: string;
  highlight?: boolean;
}) {
  return (
    <div className="stat-card" style={highlight ? { borderColor: "var(--status-partial)" } : undefined}>
      <div className="stat-value">
        {value}
        {unit && <span className="unit">{unit}</span>}
      </div>
      <div className="stat-label">{label}</div>
    </div>
  );
}
