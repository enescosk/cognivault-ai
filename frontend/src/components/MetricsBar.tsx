import type { Appointment, Metrics } from "../types/api";

type MetricsBarProps = {
  metrics: Metrics | null;
  appointments: Appointment[];
  role: string;
};

const timeFormatter = new Intl.DateTimeFormat("tr-TR", { dateStyle: "medium", timeStyle: "short" });

export function MetricsBar({ metrics, appointments, role }: MetricsBarProps) {
  const isCustomer = role === "customer";

  return (
    <div className="metrics-topbar">
      <div className="metric-cell">
        <div className="metric-label">{isCustomer ? "Oturumlarım" : "Active Sessions"}</div>
        <div className="metric-value accent">{metrics?.active_sessions ?? 0}</div>
      </div>
      <div className="metric-cell">
        <div className="metric-label">{isCustomer ? "Randevularım" : "Appointments"}</div>
        <div className="metric-value">{metrics?.confirmed_appointments ?? 0}</div>
      </div>
      {!isCustomer && (
        <div className="metric-cell">
          <div className="metric-label">Audit Events</div>
          <div className="metric-value">{metrics?.audit_events_today ?? 0}</div>
        </div>
      )}
      <div className="metric-cell">
        <div className="metric-label">{isCustomer ? "Başarı Oranı" : "Success Rate"}</div>
        <div className="metric-value green">{metrics?.completion_rate ?? 100}%</div>
      </div>
      <div className="metric-cell upcoming-cell">
        <div className="upcoming-cell-label">
          {isCustomer ? "Yaklaşan Randevularım" : "Upcoming Appointments"}
        </div>
        {appointments.filter(a => a.status === "confirmed").length === 0 ? (
          <div style={{ fontSize: "0.8rem", color: "var(--text-3)", fontFamily: "var(--font-mono)" }}>
            {isCustomer ? "Randevu yok" : "No appointments scheduled"}
          </div>
        ) : (
          appointments
            .filter(a => a.status === "confirmed")
            .slice(0, 2)
            .map((apt) => (
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
