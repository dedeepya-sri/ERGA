import { NavLink } from "react-router-dom";
import type { CriterionStatus } from "../api/types";
import { NLI_THRESHOLDS } from "../api/types";

export function NavBar() {
  const links = [
    { to: "/", label: "Dashboard", end: true },
    { to: "/assessments/new", label: "Create assessment" },
    { to: "/assessments", label: "All assessments" },
  ];
  return (
    <nav className="app-nav">
      <div className="app-nav-inner">
        <span className="nav-brand">
          ERGA<span>.</span>
        </span>
        <div className="nav-links">
          {links.map((l) => (
            <NavLink
              key={l.to}
              to={l.to}
              end={l.end}
              className={({ isActive }) => "nav-link" + (isActive ? " active" : "")}
            >
              {l.label}
            </NavLink>
          ))}
        </div>
      </div>
    </nav>
  );
}

const STATUS_LABEL: Record<CriterionStatus, string> = {
  supported: "Supported",
  partially_supported: "Partial",
  not_supported: "Missing",
};

export function StatusBadge({ status }: { status: CriterionStatus }) {
  return (
    <span className={`badge badge-${status}`}>
      <span className="badge-dot" />
      {STATUS_LABEL[status]}
    </span>
  );
}

/**
 * The recurring "confidence ledger" motif: a small ruler showing the
 * NOT_SUPPORTED / PARTIAL / SUPPORTED zones (from the actual configured
 * thresholds) with a tick at this criterion's composite score. This is a
 * literal, honest rendering of the deterministic classification, not a
 * decorative progress bar.
 */
export function ConfidenceStrip({
  score,
  label = "Composite score",
}: {
  score: number;
  label?: string;
}) {
  const { partialMin, supportedMin } = NLI_THRESHOLDS;
  const pct = Math.max(0, Math.min(100, score * 100));
  return (
    <div className="confidence-strip">
      <div className="confidence-strip-track">
        <div
          className="confidence-strip-zone-missing"
          style={{ width: `${partialMin * 100}%` }}
        />
        <div
          className="confidence-strip-zone-partial"
          style={{ width: `${(supportedMin - partialMin) * 100}%` }}
        />
        <div
          className="confidence-strip-zone-supported"
          style={{ width: `${(1 - supportedMin) * 100}%` }}
        />
        <div className="confidence-strip-marker" style={{ left: `${pct}%` }} title={`${label}: ${score.toFixed(2)}`} />
      </div>
      <div className="confidence-strip-labels">
        <span>0.0</span>
        <span>{label} {score.toFixed(2)}</span>
        <span>1.0</span>
      </div>
    </div>
  );
}

export function ConfidencePill({ value, thresholdBelow }: { value: number; thresholdBelow: number }) {
  const low = value < thresholdBelow;
  return (
    <span className={`badge ${low ? "badge-not_supported" : "badge-supported"}`}>
      <span className="badge-dot" />
      {value.toFixed(2)}
    </span>
  );
}

export function Spinner() {
  return <span className="spinner" aria-label="Loading" />;
}

export function ErrorNotice({ message }: { message: string }) {
  return (
    <div className="alert alert-danger">
      <strong>Error:</strong>&nbsp;{message}
    </div>
  );
}
