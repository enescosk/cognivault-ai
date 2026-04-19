import type { Appointment, Metrics } from "../types/api";

type MetricsBarProps = {
  metrics: Metrics | null;
  appointments: Appointment[];
};

const timeFormatter = new Intl.DateTimeFormat("en-GB", { dateStyle: "medium", timeStyle: "short" });

export function MetricsBar({ metrics, appointments }: MetricsBarProps) {
  return (
    <div className="metrics-topbar">
      <div className="metric-cell">
        <div className="metric-label">Active Sessions</div>
        <div className="metric-value accent">{metrics?.active_sessions ?? 0}</div>
      </div>
      <div className="metric-cell">
        <div className="metric-label">Appointments</div>
        <div className="metric-value">{metrics?.confirmed_appointments ?? 0}</div>
      </div>
      <div className="metric-cell">
        <div className="metric-label">Audit Events</div>
        <div className="metric-value">{metrics?.audit_events_today ?? 0}</div>
      </div>
      <div className="metric-cell">
        <div className="metric-label">Success Rate</div>
        <div className="metric-value green">{metrics?.completion_rate ?? 0}%</div>
      </div>
      <div className="metric-cell upcoming-cell">
        <div className="upcoming-cell-label">Upcoming Appointments</div>
        {appointments.length === 0 ? (
          <div style={{ fontSize: "0.8rem", color: "var(--text-3)", fontFamily: "var(--font-mono)" }}>No appointments scheduled</div>
        ) : (
          appointments.slice(0, 2).map((apt) => (
            <div className="upcoming-item-compact" key={apt.id}>
              <span className="upcoming-dept">{apt.department}</span>
              <span className="upcoming-time">{timeFormatter.format(new Date(apt.scheduled_at))}</span>
              <span className="upcoming-code">{apt.confirmation_code}</span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
