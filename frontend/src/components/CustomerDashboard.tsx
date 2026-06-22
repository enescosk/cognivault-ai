import { useMemo } from "react";
import type { Appointment, ChatSessionSummary, Metrics } from "../types/api";

type Props = {
  appointments: Appointment[];
  sessions: ChatSessionSummary[];
  metrics: Metrics | null;
  onStartChat: () => void;
  onViewAppointments: () => void;
  onViewNotes: () => void;
  onViewConversations: () => void;
};

const trDate = new Intl.DateTimeFormat("tr-TR", { dateStyle: "medium" });
const trTime = new Intl.DateTimeFormat("tr-TR", { timeStyle: "short" });

function relativeTime(dateStr: string): string {
  const diff = new Date(dateStr).getTime() - Date.now();
  const mins = Math.round(diff / 60000);
  if (mins < 0) return "Gecmis";
  if (mins < 60) return `${mins} dk sonra`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs} saat sonra`;
  const days = Math.round(hrs / 24);
  return `${days} gun sonra`;
}

// Mock appointment notes data
const MOCK_NOTES = [
  { id: 1, title: "Dis kontrolu sonrasi notlar", date: "2026-05-09T14:30:00", summary: "Dis temizligi yapildi, 6 ay sonra kontrol onerisi", doctor: "Dr. Elif Yilmaz", status: "completed" as const },
  { id: 2, title: "Cilt muayenesi degerlendirmesi", date: "2026-05-07T10:00:00", summary: "Alerjik reaksiyon tedavisi baslandi, kontrol 2 hafta sonra", doctor: "Dr. Kemal Aydin", status: "follow_up" as const },
  { id: 3, title: "Genel saglik kontrolu", date: "2026-05-05T09:00:00", summary: "Kan tahlili sonuclari normal, yillik kontrol tamamlandi", doctor: "Dr. Fatma Celik", status: "completed" as const },
];

const MOCK_TASKS = [
  { id: 1, label: "Kan tahlili sonuclarini yukle", due: "2026-05-12", done: false },
  { id: 2, label: "Recete yenilemesi icin arama yap", due: "2026-05-10", done: false },
  { id: 3, label: "Kontrol randevusu al — Dermatoloji", due: "2026-05-20", done: true },
];

export function CustomerDashboard({ appointments, sessions, metrics, onStartChat, onViewAppointments, onViewNotes, onViewConversations }: Props) {
  const upcomingAppointments = useMemo(() =>
    appointments
      .filter(a => a.status === "confirmed" && new Date(a.scheduled_at).getTime() > Date.now())
      .sort((a, b) => new Date(a.scheduled_at).getTime() - new Date(b.scheduled_at).getTime())
      .slice(0, 3),
    [appointments]
  );

  const recentSessions = useMemo(() =>
    sessions
      .filter(s => s.last_message_preview)
      .sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime())
      .slice(0, 3),
    [sessions]
  );

  const pendingTasks = MOCK_TASKS.filter(t => !t.done);

  return (
    <div className="cust-dash">
      {/* Welcome header */}
      <div className="cust-dash-header">
        <div>
          <h2 className="cust-dash-title">Hosgeldiniz</h2>
          <p className="cust-dash-subtitle">Saglik takibiniz ve randevulariniz burada</p>
        </div>
        <div className="cust-dash-header-stats">
          <div className="cust-dash-stat">
            <span className="cust-dash-stat-num">{metrics?.confirmed_appointments ?? 0}</span>
            <span className="cust-dash-stat-label">Randevu</span>
          </div>
          <div className="cust-dash-stat">
            <span className="cust-dash-stat-num">{metrics?.active_sessions ?? 0}</span>
            <span className="cust-dash-stat-label">Sohbet</span>
          </div>
          <div className="cust-dash-stat">
            <span className="cust-dash-stat-num">{pendingTasks.length}</span>
            <span className="cust-dash-stat-label">Gorev</span>
          </div>
        </div>
      </div>

      {/* Quick actions */}
      <div className="cust-dash-actions">
        <button className="cust-dash-action-btn cust-dash-action--primary" onClick={onStartChat} type="button">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/>
          </svg>
          AI Asistan ile Konusun
        </button>
        <button className="cust-dash-action-btn" onClick={onViewAppointments} type="button">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <rect x="3" y="4" width="18" height="18" rx="2"/>
            <line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/>
            <line x1="3" y1="10" x2="21" y2="10"/>
          </svg>
          Randevu Olustur
        </button>
        <button className="cust-dash-action-btn" onClick={onViewNotes} type="button">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
            <polyline points="14 2 14 8 20 8"/>
            <line x1="16" y1="13" x2="8" y2="13"/>
            <line x1="16" y1="17" x2="8" y2="17"/>
          </svg>
          Notlari Gor
        </button>
        <button className="cust-dash-action-btn" onClick={onViewConversations} type="button">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10"/>
            <path d="M12 16v-4M12 8h.01"/>
          </svg>
          Profil Guncelle
        </button>
      </div>

      {/* Main grid */}
      <div className="cust-dash-grid">
        {/* Upcoming appointments */}
        <div className="cust-dash-card">
          <div className="cust-dash-card-header">
            <h3>Yaklasan Randevular</h3>
            <button className="cust-dash-card-link" onClick={onViewAppointments} type="button">Tumunu gor</button>
          </div>
          {upcomingAppointments.length === 0 ? (
            <div className="cust-dash-card-empty">
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" style={{ opacity: 0.2 }}>
                <rect x="3" y="4" width="18" height="18" rx="2"/>
                <line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/>
                <line x1="3" y1="10" x2="21" y2="10"/>
              </svg>
              <span>Yaklasan randevunuz yok</span>
            </div>
          ) : (
            <div className="cust-dash-apt-list">
              {upcomingAppointments.map(apt => {
                const d = new Date(apt.scheduled_at);
                return (
                  <div key={apt.id} className="cust-dash-apt-item">
                    <div className="cust-dash-apt-left">
                      <span className="cust-dash-apt-dept">{apt.department}</span>
                      <span className="cust-dash-apt-date">{trDate.format(d)} — {trTime.format(d)}</span>
                      {apt.location && <span className="cust-dash-apt-loc">{apt.location}</span>}
                    </div>
                    <span className="cust-dash-apt-badge">{relativeTime(apt.scheduled_at)}</span>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Appointment notes */}
        <div className="cust-dash-card">
          <div className="cust-dash-card-header">
            <h3>Randevu Notlari</h3>
            <button className="cust-dash-card-link" onClick={onViewNotes} type="button">Tumunu gor</button>
          </div>
          <div className="cust-dash-notes-list">
            {MOCK_NOTES.slice(0, 3).map(note => (
              <div key={note.id} className="cust-dash-note-item">
                <div className="cust-dash-note-top">
                  <span className="cust-dash-note-title">{note.title}</span>
                  <span className={`cust-dash-note-status cust-dash-note-status--${note.status}`}>
                    {note.status === "completed" ? "Tamamlandi" : "Takip"}
                  </span>
                </div>
                <p className="cust-dash-note-summary">{note.summary}</p>
                <div className="cust-dash-note-meta">
                  <span>{note.doctor}</span>
                  <span>{trDate.format(new Date(note.date))}</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Recent conversations */}
        <div className="cust-dash-card">
          <div className="cust-dash-card-header">
            <h3>Son Sohbetler</h3>
            <button className="cust-dash-card-link" onClick={onViewConversations} type="button">Tumunu gor</button>
          </div>
          {recentSessions.length === 0 ? (
            <div className="cust-dash-card-empty">
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" style={{ opacity: 0.2 }}>
                <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/>
              </svg>
              <span>Henuz sohbet yok</span>
            </div>
          ) : (
            <div className="cust-dash-conv-list">
              {recentSessions.map(s => (
                <div key={s.id} className="cust-dash-conv-item">
                  <span className="cust-dash-conv-title">{s.title}</span>
                  <span className="cust-dash-conv-preview">{s.last_message_preview}</span>
                  <span className="cust-dash-conv-date">{trDate.format(new Date(s.updated_at))}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Tasks */}
        <div className="cust-dash-card">
          <div className="cust-dash-card-header">
            <h3>Gorevler ve Talepler</h3>
          </div>
          <div className="cust-dash-tasks-list">
            {MOCK_TASKS.map(task => (
              <div key={task.id} className={`cust-dash-task-item ${task.done ? "cust-dash-task--done" : ""}`}>
                <span className={`cust-dash-task-check ${task.done ? "cust-dash-task-check--done" : ""}`}>
                  {task.done ? "✓" : ""}
                </span>
                <div className="cust-dash-task-info">
                  <span className="cust-dash-task-label">{task.label}</span>
                  <span className="cust-dash-task-due">Son tarih: {trDate.format(new Date(task.due))}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
