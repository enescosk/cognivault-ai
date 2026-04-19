import type { Appointment } from "../types/api";

type Props = { appointments: Appointment[] };

const dateFormatter = new Intl.DateTimeFormat("tr-TR", { dateStyle: "medium", timeStyle: "short" });

function safeFormat(d: string) {
  const date = new Date(d);
  return isNaN(date.getTime()) ? "—" : dateFormatter.format(date);
}

const statusConfig: Record<string, { label: string; color: string; bg: string }> = {
  confirmed: { label: "Onaylandı", color: "var(--green)", bg: "var(--green-bg)" },
  pending: { label: "Bekliyor", color: "var(--amber)", bg: "var(--amber-bg)" },
  cancelled: { label: "İptal", color: "var(--red)", bg: "var(--red-bg)" },
};

export function AppointmentPanel({ appointments }: Props) {
  return (
    <aside className="appointment-panel">
      <div className="apanel-header">
        <div className="apanel-title-row">
          <span className="apanel-title">Randevularım</span>
          <span className="apanel-count">{appointments.length}</span>
        </div>
        <div className="apanel-subtitle">Aktif ve geçmiş randevularınız</div>
      </div>

      {appointments.length === 0 ? (
        <div className="apanel-empty">
          <div className="apanel-empty-icon">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <rect x="3" y="4" width="18" height="18" rx="2" ry="2"/>
              <line x1="16" y1="2" x2="16" y2="6"/>
              <line x1="8" y1="2" x2="8" y2="6"/>
              <line x1="3" y1="10" x2="21" y2="10"/>
            </svg>
          </div>
          <p>Henüz randevunuz yok</p>
          <span>Sohbet üzerinden randevu alabilirsiniz</span>
        </div>
      ) : (
        <div className="apanel-list">
          {appointments.map((apt) => {
            const status = statusConfig[apt.status] ?? statusConfig.pending;
            return (
              <div className="apanel-card" key={apt.id}>
                <div className="apanel-card-top">
                  <div className="apanel-dept">{apt.department}</div>
                  <span className="apanel-status" style={{ color: status.color, background: status.bg }}>
                    {status.label}
                  </span>
                </div>
                <div className="apanel-code">{apt.confirmation_code}</div>
                <div className="apanel-info-grid">
                  <div className="apanel-info-item">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <circle cx="12" cy="12" r="10"/>
                      <polyline points="12 6 12 12 16 14"/>
                    </svg>
                    {safeFormat(apt.scheduled_at)}
                  </div>
                  <div className="apanel-info-item">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0118 0z"/>
                      <circle cx="12" cy="10" r="3"/>
                    </svg>
                    {apt.location}
                  </div>
                </div>
                {apt.purpose && (
                  <div className="apanel-purpose">{apt.purpose}</div>
                )}
              </div>
            );
          })}
        </div>
      )}

      <div className="apanel-footer">
        <div className="apanel-footer-tip">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10"/>
            <line x1="12" y1="8" x2="12" y2="12"/>
            <line x1="12" y1="16" x2="12.01" y2="16"/>
          </svg>
          Randevu almak veya iptal etmek için sohbet kutusunu kullanın
        </div>
      </div>
    </aside>
  );
}
