import type { Appointment } from "../types/api";

type Props = { appointments: Appointment[] };

const trTime = new Intl.DateTimeFormat("tr-TR", { timeStyle: "short" });
const trDate = new Intl.DateTimeFormat("tr-TR", { dateStyle: "medium" });

function safeDate(s: string) {
  const d = new Date(s);
  return isNaN(d.getTime()) ? null : d;
}

function isActiveNow(s: string) {
  const d = safeDate(s);
  if (!d) return false;
  const diff = d.getTime() - Date.now();
  return diff >= -30 * 60 * 1000 && diff <= 60 * 60 * 1000;
}

function isUpcoming(s: string) {
  const d = safeDate(s);
  if (!d) return false;
  const diff = d.getTime() - Date.now();
  return diff > 60 * 60 * 1000 && diff <= 24 * 60 * 60 * 1000;
}

export function OperatorPanel({ appointments }: Props) {
  const active   = appointments.filter(a => a.status === "confirmed" && isActiveNow(a.scheduled_at));
  const upcoming = appointments.filter(a => a.status === "confirmed" && isUpcoming(a.scheduled_at))
                               .sort((a, b) => new Date(a.scheduled_at).getTime() - new Date(b.scheduled_at).getTime());

  return (
    <aside className="audit-panel operator-panel">
      {/* Header */}
      <div className="audit-header">
        <div className="audit-header-row">
          <span className="audit-title">Operatör Paneli</span>
          <span className="op-badge">
            <span className="active-apt-dot" style={{ width: 6, height: 6 }} />
            Canlı
          </span>
        </div>
        <div className="audit-subtitle">
          {active.length > 0 ? `${active.length} aktif · ` : ""}{upcoming.length} yaklaşan randevu
        </div>
      </div>

      {/* Aktif randevu */}
      {active.length > 0 && (
        <div className="op-section">
          <div className="op-section-label">
            <span className="active-apt-dot" />
            Şu An Aktif
          </div>
          {active.map(apt => {
            const d = safeDate(apt.scheduled_at)!;
            return (
              <div className="op-active-card" key={apt.id}>
                {apt.user_name && (
                  <div className="op-who">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2"/><circle cx="12" cy="7" r="4"/>
                    </svg>
                    {apt.user_name}
                  </div>
                )}
                <div className="op-active-dept">{apt.department}</div>
                <div className="op-active-meta">
                  <span className="op-code">{apt.confirmation_code}</span>
                  <span className="op-time">{trDate.format(d)}, {trTime.format(d)}</span>
                </div>
                {apt.location && (
                  <div className="op-row">
                    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0118 0z"/><circle cx="12" cy="10" r="3"/>
                    </svg>
                    {apt.location}
                  </div>
                )}
                {apt.purpose && <div className="op-purpose">{apt.purpose}</div>}
                {apt.contact_phone && (
                  <div className="op-row op-phone">
                    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M22 16.92v3a2 2 0 01-2.18 2 19.79 19.79 0 01-8.63-3.07A19.5 19.5 0 013.07 9.81a19.79 19.79 0 01-3.07-8.68A2 2 0 012 .18h3a2 2 0 012 1.72c.127.96.361 1.903.7 2.81a2 2 0 01-.45 2.11L6.09 7.91a16 16 0 006 6l1.27-1.27a2 2 0 012.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0122 16.92z"/>
                    </svg>
                    {apt.contact_phone}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Yaklaşan randevular */}
      {upcoming.length > 0 && (
        <div className="op-section">
          <div className="op-section-label">Yaklaşan Randevular</div>
          <div className="op-queue">
            {upcoming.slice(0, 5).map(apt => {
              const d = safeDate(apt.scheduled_at)!;
              return (
                <div className="op-queue-row" key={apt.id}>
                  <div className="op-queue-time">{trTime.format(d)}</div>
                  <div className="op-queue-info">
                    <span className="op-queue-dept">{apt.department}</span>
                    <span className="op-queue-loc">
                      {apt.user_name ?? "—"}
                      {apt.location ? ` · ${apt.location}` : ""}
                    </span>
                  </div>
                  <span className="op-code" style={{ fontSize: "0.65rem" }}>{apt.confirmation_code}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Hiç randevu yoksa */}
      {active.length === 0 && upcoming.length === 0 && (
        <div className="op-empty">
          <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" style={{ opacity: 0.25 }}>
            <rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/>
          </svg>
          <p>Bugün aktif randevu yok</p>
        </div>
      )}

      {/* Tüm randevuların özeti */}
      <div className="op-section op-section--border">
        <div className="op-section-label">Tüm Randevular</div>
        {appointments.length === 0 ? (
          <div className="op-empty" style={{ padding: "12px 0" }}>Randevu bulunamadı</div>
        ) : (
          <div className="op-queue">
            {appointments.map(apt => {
              const d = safeDate(apt.scheduled_at);
              const nowActive = isActiveNow(apt.scheduled_at);
              const statusColors: Record<string, string> = {
                confirmed: "var(--green)",
                cancelled: "var(--red)",
                pending: "var(--amber)",
              };
              return (
                <div className={`op-queue-row ${nowActive ? "op-queue-row--active" : ""}`} key={apt.id}>
                  <div className="op-queue-time">
                    {nowActive && <span className="active-apt-dot" style={{ width: 6, height: 6, marginRight: 4 }} />}
                    {d ? trTime.format(d) : "—"}
                  </div>
                  <div className="op-queue-info">
                    <span className="op-queue-dept">{apt.department}</span>
                    {apt.location && <span className="op-queue-loc">{apt.location}</span>}
                  </div>
                  <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.65rem", color: statusColors[apt.status] ?? "var(--text-3)" }}>
                    {apt.status === "confirmed" ? "Onaylı" : apt.status === "cancelled" ? "İptal" : "Bekliyor"}
                  </span>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </aside>
  );
}
