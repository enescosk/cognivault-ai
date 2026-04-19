import type { Appointment, AuditLog } from "../types/api";

type AuditLogPanelProps = {
  logs: AuditLog[];
  appointments: Appointment[];
  role?: "operator" | "admin";
};

const timeFormatter = new Intl.DateTimeFormat("en-GB", { dateStyle: "short", timeStyle: "short" });
const trTimeFormatter = new Intl.DateTimeFormat("tr-TR", { timeStyle: "short" });
const trDateFormatter = new Intl.DateTimeFormat("tr-TR", { dateStyle: "medium" });

function safeFormat(dateStr: string | null | undefined): string {
  if (!dateStr) return "—";
  const d = new Date(dateStr);
  if (isNaN(d.getTime())) return "—";
  return timeFormatter.format(d);
}

function isActiveNow(dateStr: string): boolean {
  const apt = new Date(dateStr);
  const now = new Date();
  const diffMs = apt.getTime() - now.getTime();
  // -30 dakika ile +60 dakika aralığında = "şu an aktif"
  return diffMs >= -30 * 60 * 1000 && diffMs <= 60 * 60 * 1000;
}

export function AuditLogPanel({ logs, appointments, role = "operator" }: AuditLogPanelProps) {
  const activeAppointments = appointments.filter(a => a.status === "confirmed" && isActiveNow(a.scheduled_at));
  const isAdmin = role === "admin";
  function handleExport() {
    const blob = new Blob([JSON.stringify(logs, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `audit-${new Date().toISOString().split("T")[0]}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <aside className="audit-panel">
      <div className="audit-header">
        <div className="audit-header-row">
          <span className="audit-title">{isAdmin ? "Sistem Paneli" : "Audit Trail"}</span>
          <button className="export-btn" onClick={handleExport} type="button">
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/>
              <polyline points="7 10 12 15 17 10"/>
              <line x1="12" y1="15" x2="12" y2="3"/>
            </svg>
            Export
          </button>
        </div>
        <div className="audit-subtitle">
          {isAdmin
            ? `${appointments.length} randevu · ${logs.length} audit kaydı`
            : `Canlı aktivite · ${logs.length} olay`}
        </div>
      </div>

      {/* Admin: tüm randevuların özeti */}
      {isAdmin && (
        <div className="admin-apt-summary">
          <div className="audit-section-label">Tüm Randevular</div>
          <div className="admin-apt-list">
            {appointments.length === 0 ? (
              <div className="admin-apt-empty">Randevu bulunamadı</div>
            ) : (
              appointments.slice(0, 5).map((apt) => (
                <div className={`admin-apt-row ${isActiveNow(apt.scheduled_at) ? "admin-apt-row--active" : ""}`} key={apt.id}>
                  <div className="admin-apt-row-left">
                    {isActiveNow(apt.scheduled_at) && <span className="active-apt-dot" style={{ marginRight: 6 }} />}
                    <span className="admin-apt-dept">{apt.department}</span>
                  </div>
                  <div className="admin-apt-row-right">
                    <span className="admin-apt-code">{apt.confirmation_code}</span>
                    <span className="admin-apt-time">{trTimeFormatter.format(new Date(apt.scheduled_at))}</span>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      )}
      {activeAppointments.length > 0 && (
        <div className="active-apt-section">
          <div className="active-apt-label">
            <span className="active-apt-dot" />
            Şu An Aktif Randevu
          </div>
          {activeAppointments.map((apt) => {
            const aptDate = new Date(apt.scheduled_at);
            return (
              <div className="active-apt-card" key={apt.id}>
                <div className="active-apt-dept">{apt.department}</div>
                <div className="active-apt-meta">
                  <span className="active-apt-code">{apt.confirmation_code}</span>
                  <span className="active-apt-time">
                    {trDateFormatter.format(aptDate)}, {trTimeFormatter.format(aptDate)}
                  </span>
                </div>
                {apt.location && (
                  <div className="active-apt-location">
                    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0118 0z"/><circle cx="12" cy="10" r="3"/>
                    </svg>
                    {apt.location}
                  </div>
                )}
                {apt.purpose && (
                  <div className="active-apt-purpose">{apt.purpose}</div>
                )}
              </div>
            );
          })}
        </div>
      )}
      <div className="audit-section-label">Recent Events</div>
      <div className="audit-list">
        {logs.length === 0 ? (
          <div style={{ padding: "20px 12px", color: "var(--text-3)", fontSize: "0.82rem", textAlign: "center", fontFamily: "var(--font-mono)" }}>
            No events recorded
          </div>
        ) : (
          logs.slice(0, 40).map((log) => (
            <div className="audit-item" key={log.id}>
              <div className="audit-item-top">
                <span className="audit-action">{log.action_type}</span>
                <span className="audit-time">{safeFormat(log.created_at ?? log.timestamp)}</span>
              </div>
              <div className="audit-desc">{log.explanation}</div>
              <div className={`audit-status ${log.result_status === "success" ? "" : "fail"}`}>
                <span className="audit-status-dot" />
                {log.result_status}
              </div>
            </div>
          ))
        )}
      </div>
      {appointments.length > 0 && (
        <div className="confirmations-section">
          <div className="audit-section-label" style={{ padding: "14px 20px 8px" }}>Recent Confirmations</div>
          <div className="confirmations-list">
            {appointments.slice(0, 3).map((apt) => (
              <div className="confirmation-item" key={apt.id}>
                <div className="confirmation-item-code">{apt.confirmation_code}</div>
                <div className="confirmation-item-dept">{apt.department}</div>
                <div className="confirmation-item-time">{safeFormat(apt.scheduled_at)}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </aside>
  );
}
