import type { Appointment, AuditLog } from "../types/api";

type AuditLogPanelProps = {
  logs: AuditLog[];
  appointments: Appointment[];
};

const formatter = new Intl.DateTimeFormat("en-GB", {
  dateStyle: "medium",
  timeStyle: "short"
});

export function AuditLogPanel({ logs, appointments }: AuditLogPanelProps) {
  function exportLogs() {
    const blob = new Blob([JSON.stringify(logs, null, 2)], {
      type: "application/json"
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "cognivault-audit-log.json";
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <aside className="audit-panel">
      <div className="sidebar-card">
        <div className="sidebar-section-header">
          <div>
            <div className="eyebrow">Oversight</div>
            <h3>Audit Trail</h3>
          </div>
          <button className="ghost-button" onClick={exportLogs} type="button">
            Export JSON
          </button>
        </div>

        <div className="audit-list">
          {logs.slice(0, 10).map((log) => (
            <div className="audit-item" key={log.id}>
              <div className="audit-topline">
                <span className={`status-badge ${log.success ? "success" : "warning"}`}>
                  {log.result_status}
                </span>
                <small>{formatter.format(new Date(log.timestamp))}</small>
              </div>
              <strong>{log.action_type}</strong>
              <p>{log.explanation}</p>
              {log.tool_name ? <code>{log.tool_name}</code> : null}
            </div>
          ))}
        </div>
      </div>

      <div className="sidebar-card">
        <div className="eyebrow">Records</div>
        <h3>Recent Confirmations</h3>
        <div className="upcoming-list">
          {appointments.slice(0, 4).map((appointment) => (
            <div className="upcoming-item" key={appointment.id}>
              <strong>{appointment.confirmation_code}</strong>
              <span>{appointment.department}</span>
              <small>{formatter.format(new Date(appointment.scheduled_at))}</small>
            </div>
          ))}
          {appointments.length === 0 ? <p className="muted">No records available.</p> : null}
        </div>
      </div>
    </aside>
  );
}
