import { useState } from "react";
import type { Appointment, AuditLog, User } from "../types/api";

type Props = { users: User[]; appointments: Appointment[]; logs: AuditLog[] };

const trTime = new Intl.DateTimeFormat("tr-TR", { timeStyle: "short" });
const trDate = new Intl.DateTimeFormat("tr-TR", { dateStyle: "long" });
const trDateTime = new Intl.DateTimeFormat("tr-TR", { dateStyle: "medium", timeStyle: "short" });

function safeDate(s: string | null | undefined) {
  if (!s) return null;
  const d = new Date(s);
  return isNaN(d.getTime()) ? null : d;
}

function isActiveNow(s: string) {
  const d = safeDate(s);
  if (!d) return false;
  const diff = d.getTime() - Date.now();
  return diff >= -30 * 60 * 1000 && diff <= 60 * 60 * 1000;
}

const roleStyle: Record<string, { color: string; bg: string }> = {
  admin:    { color: "#b794f4", bg: "rgba(183,148,244,0.12)" },
  operator: { color: "#f6ad55", bg: "rgba(246,173,85,0.12)" },
  customer: { color: "#63b3ed", bg: "rgba(99,179,237,0.12)" },
};

const statusLabel: Record<string, { label: string; color: string }> = {
  confirmed: { label: "Onaylı",  color: "var(--green)" },
  cancelled: { label: "İptal",   color: "var(--red)"   },
  pending:   { label: "Bekliyor", color: "var(--amber)" },
};

function lastLogin(userId: number, logs: AuditLog[]): string {
  const entry = logs.find(l => l.action_type === "auth.login" && l.user_id === userId);
  if (!entry) return "Giriş kaydı yok";
  const d = safeDate(entry.created_at ?? entry.timestamp);
  return d ? trDateTime.format(d) : "—";
}

function handleExport(logs: AuditLog[]) {
  const blob = new Blob([JSON.stringify(logs, null, 2)], { type: "application/json" });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement("a");
  a.href = url; a.download = `audit-${new Date().toISOString().split("T")[0]}.json`;
  a.click(); URL.revokeObjectURL(url);
}

export function AdminPanel({ users, appointments, logs }: Props) {
  const [selected, setSelected] = useState<User | null>(null);
  const activeApts = appointments.filter(a => a.status === "confirmed" && isActiveNow(a.scheduled_at));

  const sortedUsers = [...users].sort((a, b) => {
    const la = logs.findIndex(l => l.action_type === "auth.login" && l.user_id === a.id);
    const lb = logs.findIndex(l => l.action_type === "auth.login" && l.user_id === b.id);
    return (la === -1 ? 999 : la) - (lb === -1 ? 999 : lb);
  });

  // ── Kullanıcı detay görünümü ──────────────────────────────────
  if (selected) {
    const rc    = roleStyle[selected.role.name] ?? roleStyle.customer;
    const initials = selected.full_name.split(" ").map(n => n[0]).join("").toUpperCase().slice(0, 2);
    const userApts  = appointments.filter(a => a.user_id === selected.id)
                                  .sort((a, b) => new Date(b.scheduled_at).getTime() - new Date(a.scheduled_at).getTime());
    const loginTime = lastLogin(selected.id, logs);

    return (
      <aside className="audit-panel admin-panel">
        {/* Geri butonu + başlık */}
        <div className="audit-header">
          <div className="audit-header-row">
            <button className="adm-back-btn" onClick={() => setSelected(null)} type="button">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="15 18 9 12 15 6"/>
              </svg>
              Geri
            </button>
          </div>
        </div>

        {/* Kullanıcı profil kartı */}
        <div className="adm-detail-profile">
          <div className="adm-detail-avatar" style={{ background: rc.bg, color: rc.color }}>
            {initials}
          </div>
          <div className="adm-detail-name">{selected.full_name}</div>
          <div className="adm-detail-email">{selected.email}</div>
          <div className="adm-detail-badges">
            <span className="adm-role-badge" style={{ color: rc.color, background: rc.bg }}>
              {selected.role.name}
            </span>
            {selected.department && (
              <span className="adm-dept-badge">{selected.department}</span>
            )}
          </div>
          <div className="adm-detail-meta">
            <div className="adm-detail-meta-item">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>
              </svg>
              Son giriş: {loginTime}
            </div>
            <div className="adm-detail-meta-item">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/>
              </svg>
              {userApts.length} randevu kaydı
            </div>
          </div>
        </div>

        {/* Randevu geçmişi */}
        <div className="adm-section-label">Randevu Geçmişi</div>
        <div className="adm-apt-detail-list">
          {userApts.length === 0 ? (
            <div className="adm-detail-empty">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" style={{ opacity: 0.2 }}>
                <rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/>
              </svg>
              <p>Randevu bulunamadı</p>
            </div>
          ) : (
            userApts.map(apt => {
              const d      = safeDate(apt.scheduled_at);
              const active = isActiveNow(apt.scheduled_at);
              const st     = statusLabel[apt.status] ?? statusLabel.pending;
              return (
                <div className={`adm-apt-detail-card ${active ? "adm-apt-detail-card--active" : ""}`} key={apt.id}>
                  {/* Üst satır: tarih + saat + durum */}
                  <div className="adm-apt-detail-top">
                    <div className="adm-apt-detail-when">
                      {active && <span className="active-apt-dot" style={{ width: 6, height: 6, marginRight: 5 }} />}
                      {d ? (
                        <>
                          <span className="adm-apt-detail-date">{trDate.format(d)}</span>
                          <span className="adm-apt-detail-time">{trTime.format(d)}</span>
                        </>
                      ) : "—"}
                    </div>
                    <span className="adm-apt-detail-status" style={{ color: st.color }}>{st.label}</span>
                  </div>

                  {/* Departman */}
                  <div className="adm-apt-detail-dept">{apt.department}</div>

                  {/* Meta bilgiler */}
                  <div className="adm-apt-detail-grid">
                    {apt.location && (
                      <div className="adm-apt-detail-row">
                        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0118 0z"/><circle cx="12" cy="10" r="3"/>
                        </svg>
                        {apt.location}
                      </div>
                    )}
                    {apt.contact_phone && (
                      <div className="adm-apt-detail-row">
                        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M22 16.92v3a2 2 0 01-2.18 2 19.79 19.79 0 01-8.63-3.07A19.5 19.5 0 013.07 9.81a19.79 19.79 0 01-3.07-8.68A2 2 0 012 .18h3a2 2 0 012 1.72c.127.96.361 1.903.7 2.81a2 2 0 01-.45 2.11L6.09 7.91a16 16 0 006 6l1.27-1.27a2 2 0 012.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0122 16.92z"/>
                        </svg>
                        {apt.contact_phone}
                      </div>
                    )}
                    <div className="adm-apt-detail-row">
                      <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
                      </svg>
                      {apt.confirmation_code}
                    </div>
                  </div>

                  {/* Amaç */}
                  {apt.purpose && (
                    <div className="adm-apt-detail-purpose">{apt.purpose}</div>
                  )}
                  {apt.notes && (
                    <div className="adm-apt-detail-notes">{apt.notes}</div>
                  )}
                </div>
              );
            })
          )}
        </div>
      </aside>
    );
  }

  // ── Ana liste görünümü ────────────────────────────────────────
  return (
    <aside className="audit-panel admin-panel">
      <div className="audit-header">
        <div className="audit-header-row">
          <span className="audit-title">Sistem Paneli</span>
          <button className="export-btn" onClick={() => handleExport(logs)} type="button">
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/>
              <polyline points="7 10 12 15 17 10"/>
              <line x1="12" y1="15" x2="12" y2="3"/>
            </svg>
            Export
          </button>
        </div>
        <div className="audit-subtitle">{users.length} kullanıcı · {appointments.length} randevu · {logs.length} olay</div>
      </div>

      {activeApts.length > 0 && (
        <div className="admin-active-banner">
          <span className="active-apt-dot" />
          <span>{activeApts.length} randevu şu an aktif</span>
          <span className="admin-active-codes">{activeApts.map(a => a.confirmation_code).join(" · ")}</span>
        </div>
      )}

      <div className="adm-section-label">Sistem Kullanıcıları</div>
      <div className="adm-user-list">
        {sortedUsers.map(u => {
          const rc = roleStyle[u.role.name] ?? roleStyle.customer;
          const initials = u.full_name.split(" ").map(n => n[0]).join("").toUpperCase().slice(0, 2);
          const login = lastLogin(u.id, logs);
          return (
            <div className="adm-user-row adm-user-row--clickable" key={u.id} onClick={() => setSelected(u)}>
              <div className="adm-avatar" style={{ background: rc.bg, color: rc.color }}>{initials}</div>
              <div className="adm-user-info">
                <div className="adm-user-name">{u.full_name}</div>
                <div className="adm-user-email">{u.email}</div>
              </div>
              <div className="adm-user-right">
                <span className="adm-role-badge" style={{ color: rc.color, background: rc.bg }}>{u.role.name}</span>
                <span className="adm-last-login">{login}</span>
              </div>
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" style={{ opacity: 0.25, flexShrink: 0 }}>
                <polyline points="9 18 15 12 9 6"/>
              </svg>
            </div>
          );
        })}
      </div>

      <div className="adm-section-label" style={{ marginTop: 4 }}>Randevular</div>
      <div className="adm-apt-list">
        {appointments.length === 0 ? (
          <div className="adm-empty">Randevu bulunamadı</div>
        ) : (
          appointments.slice(0, 6).map(apt => {
            const d = safeDate(apt.scheduled_at);
            const active = isActiveNow(apt.scheduled_at);
            return (
              <div className={`adm-apt-row ${active ? "adm-apt-row--active" : ""}`} key={apt.id}>
                <div className="adm-apt-left">
                  {active && <span className="active-apt-dot" style={{ width: 6, height: 6, marginRight: 6 }} />}
                  <div>
                    <div className="adm-apt-dept">{apt.department}</div>
                    {apt.user_name && <div style={{ fontSize: "0.68rem", color: "rgba(255,255,255,0.3)" }}>{apt.user_name}</div>}
                  </div>
                </div>
                <div className="adm-apt-right">
                  <span className="adm-apt-code">{apt.confirmation_code}</span>
                  {d && <span className="adm-apt-time">{trTime.format(d)}</span>}
                </div>
              </div>
            );
          })
        )}
      </div>
    </aside>
  );
}
