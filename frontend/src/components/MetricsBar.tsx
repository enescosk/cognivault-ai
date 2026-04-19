import type { Appointment, Metrics } from "../types/api";

type MetricsBarProps = {
  metrics: Metrics | null;
  appointments: Appointment[];
};

const formatter = new Intl.DateTimeFormat("en-GB", {
  dateStyle: "medium",
  timeStyle: "short"
});

export function MetricsBar({ metrics, appointments }: MetricsBarProps) {
  const cards = [
    {
      label: "Active Sessions",
      value: metrics?.active_sessions ?? 0
    },
    {
      label: "Confirmed Appointments",
      value: metrics?.confirmed_appointments ?? 0
    },
    {
      label: "Audit Events Today",
      value: metrics?.audit_events_today ?? 0
    },
    {
      label: "Tool Success Rate",
      value: `${metrics?.completion_rate ?? 0}%`
    }
  ];

  return (
    <div className="top-stack">
      <section className="metric-grid">
        {cards.map((card) => (
          <div className="metric-card" key={card.label}>
            <span>{card.label}</span>
            <strong>{card.value}</strong>
          </div>
        ))}
      </section>

      <section className="upcoming-card">
        <div className="sidebar-section-header">
          <div>
            <div className="eyebrow">Pipeline</div>
            <h3>Upcoming Appointments</h3>
          </div>
        </div>
        <div className="upcoming-list">
          {appointments.slice(0, 3).map((appointment) => (
            <div className="upcoming-item" key={appointment.id}>
              <strong>{appointment.department}</strong>
              <span>{formatter.format(new Date(appointment.scheduled_at))}</span>
              <small>{appointment.confirmation_code}</small>
            </div>
          ))}
          {appointments.length === 0 ? <p className="muted">No appointments yet.</p> : null}
        </div>
      </section>
    </div>
  );
}
