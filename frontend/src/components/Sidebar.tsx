import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { Appointment, ChatSessionSummary, User } from "../types/api";

type SidebarProps = {
  user: User;
  sessions: ChatSessionSummary[];
  appointments: Appointment[];
  selectedSessionId?: number;
  activeView: "chat" | "appointments" | "enterprise";
  onSelectSession: (sessionId: number) => void;
  onNewSession: () => void;
  onDeleteSession: (sessionId: number) => void;
  onViewAppointments: () => void;
  onViewEnterprise: () => void;
  onUpdateLocale: (locale: "tr" | "en") => Promise<void>;
  onLogout: () => void;
};

type MenuPos = { top: number; left: number };

const menuDateTime = new Intl.DateTimeFormat("tr-TR", { dateStyle: "short", timeStyle: "short" });

function safeAppointmentDate(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

function minutesUntilAppointment(value: string) {
  const date = safeAppointmentDate(value);
  if (!date) return Number.POSITIVE_INFINITY;
  return (date.getTime() - Date.now()) / 60000;
}

function isActiveAppointment(appointment: Appointment) {
  const minutes = minutesUntilAppointment(appointment.scheduled_at);
  return appointment.status === "confirmed" && minutes >= -30 && minutes <= 60;
}

function isUpcomingAppointment(appointment: Appointment) {
  const minutes = minutesUntilAppointment(appointment.scheduled_at);
  return appointment.status === "confirmed" && minutes > 60;
}

function statusLabel(status: string) {
  const labels: Record<string, string> = {
    confirmed: "Onaylı",
    pending: "Bekliyor",
    cancelled: "İptal",
  };
  return labels[status] ?? status;
}

export function Sidebar({ user, sessions, appointments, selectedSessionId, activeView, onSelectSession, onNewSession, onDeleteSession, onViewAppointments, onViewEnterprise, onUpdateLocale, onLogout }: SidebarProps) {
  const initials = user.full_name.split(" ").map((n) => n[0]).join("").toUpperCase().slice(0, 2);
  const roleName = user.role.name.toLowerCase();
  const en = user.locale === "en";
  const [language, setLanguage] = useState<"tr" | "en">(user.locale === "tr" ? "tr" : "en");
  const [languageSaving, setLanguageSaving] = useState(false);
  const [notifications, setNotifications] = useState(true);
  const [compact, setCompact] = useState(false);
  const [width, setWidth] = useState(280);
  const [hoveredSession, setHoveredSession] = useState<number | null>(null);
  const [openMenu, setOpenMenu] = useState<{ id: number; pos: MenuPos } | null>(null);
  const [settingsPos, setSettingsPos] = useState<MenuPos | null>(null);
  const [showSupport, setShowSupport] = useState(false);
  const [showMainMenu, setShowMainMenu] = useState(false);
  const isEnterpriseUser = user.role.name === "operator" || user.role.name === "admin";
  const operatorActiveAppointments = appointments.filter(isActiveAppointment);
  const operatorUpcomingAppointments = appointments
    .filter(isUpcomingAppointment)
    .sort((a, b) => new Date(a.scheduled_at).getTime() - new Date(b.scheduled_at).getTime());
  const operatorMenuAppointments = [...operatorActiveAppointments, ...operatorUpcomingAppointments].slice(0, 4);
  const resizing = useRef(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const settingsRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setLanguage(user.locale === "tr" ? "tr" : "en");
  }, [user.locale]);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setOpenMenu(null);
      }
      if (settingsRef.current && !settingsRef.current.contains(e.target as Node)) {
        setSettingsPos(null);
      }
    }
    if (openMenu || settingsPos) document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [openMenu, settingsPos]);

  function handleSettingsClick(e: React.MouseEvent) {
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
    setSettingsPos({ top: rect.top - 8, left: rect.left });
  }

  function startResize(e: React.MouseEvent) {
    resizing.current = true;
    const startX = e.clientX;
    const startW = width;
    function onMove(ev: MouseEvent) {
      if (!resizing.current) return;
      setWidth(Math.min(400, Math.max(200, startW + ev.clientX - startX)));
    }
    function onUp() {
      resizing.current = false;
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    }
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  }

  function handleDotsClick(e: React.MouseEvent, sessionId: number) {
    e.stopPropagation();
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
    setOpenMenu({ id: sessionId, pos: { top: rect.bottom + 4, left: rect.left - 160 } });
  }

  async function handleLanguageChange(nextLocale: "tr" | "en") {
    setLanguage(nextLocale);
    setLanguageSaving(true);
    try {
      await onUpdateLocale(nextLocale);
    } finally {
      setLanguageSaving(false);
    }
  }

  return (
    <aside className="sidebar" style={{ width, minWidth: width, maxWidth: width }}>
      <div className="sidebar-top">
        <div className="sidebar-brand">
          <div className="sidebar-brand-icon">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 2L2 7l10 5 10-5-10-5z"/>
              <path d="M2 17l10 5 10-5"/>
              <path d="M2 12l10 5 10-5"/>
            </svg>
          </div>
          <span className="sidebar-brand-name">Cognivault</span>
          <button
            className="hamburger-menu-btn"
            type="button"
            onClick={() => setShowMainMenu(true)}
            aria-label={en ? "Open menu" : "Menüyü aç"}
            title={en ? "Menu" : "Menü"}
          >
            <span />
            <span />
            <span />
          </button>
        </div>
        <div className="sidebar-profile">
          <div className="sidebar-avatar">{initials}</div>
          <div className="sidebar-name">{user.full_name}</div>
          <div className="sidebar-meta">
            <span className={`role-badge ${roleName}`}>{roleName}</span>
            <span className="sidebar-dept">{user.locale.toUpperCase()}</span>
          </div>
          <div className="sidebar-email">{user.email}</div>
        </div>
      </div>

      <div className="sidebar-body">
        <nav className="sidebar-nav">
          <div className="nav-section-label">Workspace</div>

          {/* Randevularım nav item — sadece customer için */}
          {user.role.name === "customer" && (
            <button
              className={`sidebar-nav-item ${activeView === "appointments" ? "sidebar-nav-item--active" : ""}`}
              type="button"
              onClick={onViewAppointments}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <rect x="3" y="4" width="18" height="18" rx="2"/>
                <line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/>
                <line x1="3" y1="10" x2="21" y2="10"/>
              </svg>
              {en ? "My Appointments" : "Randevularım"}
            </button>
          )}

          {(user.role.name === "operator" || user.role.name === "admin") && (
            <button
              className={`sidebar-nav-item ${activeView === "enterprise" ? "sidebar-nav-item--active" : ""}`}
              type="button"
              onClick={onViewEnterprise}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M3 21h18"/>
                <path d="M5 21V7l8-4v18"/>
                <path d="M19 21V11l-6-4"/>
                <path d="M9 9h1M9 13h1M9 17h1M15 13h1M15 17h1"/>
              </svg>
              Enterprise Panel
            </button>
          )}

          {isEnterpriseUser ? (
            <div className="enterprise-nav-card">
              <span>Operator workspace</span>
              <strong>{en ? "Enterprise requests are managed in the Enterprise Panel." : "Kurumsal talepler Enterprise Panel üzerinden yönetilir."}</strong>
              <button type="button" onClick={onViewEnterprise}>{en ? "Go to intake" : "Intake ekranına git"}</button>
            </div>
          ) : (
            <>
              <button className="nav-new-btn" onClick={() => { onNewSession(); }} type="button">
                <span>{en ? "New Session" : "Yeni Oturum"}</span>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <line x1="12" y1="5" x2="12" y2="19"/>
                  <line x1="5" y1="12" x2="19" y2="12"/>
                </svg>
              </button>
              <div className="nav-section-label">Sessions</div>
              {sessions.length === 0 ? (
                <div style={{ padding: "10px 12px", fontSize: "0.82rem", color: "var(--text-3)" }}>{en ? "No sessions yet" : "Henüz oturum yok"}</div>
              ) : (
                sessions.map((session) => (
                  <div
                    key={session.id}
                    className="session-item-wrapper"
                    onMouseEnter={() => setHoveredSession(session.id)}
                    onMouseLeave={() => setHoveredSession(null)}
                  >
                    <button
                      className={`session-item ${selectedSessionId === session.id ? "active" : ""}`}
                      onClick={() => onSelectSession(session.id)}
                      type="button"
                    >
                      <span className="session-title">{session.title}</span>
                      <span className="session-preview">{session.last_message_preview ?? (en ? "No activity yet" : "Henüz aktivite yok")}</span>
                    </button>
                    <button
                      className="session-dots-btn"
                      type="button"
                      onClick={(e) => handleDotsClick(e, session.id)}
                    >
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                        <circle cx="5" cy="12" r="2"/><circle cx="12" cy="12" r="2"/><circle cx="19" cy="12" r="2"/>
                      </svg>
                    </button>
                  </div>
                ))
              )}
            </>
          )}
        </nav>

      </div>

      <div className="sidebar-bottom">
        <button className="settings-btn" onClick={handleSettingsClick} type="button">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="3"/>
            <path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z"/>
          </svg>
          {en ? "Settings" : "Ayarlar"}
        </button>
      </div>

      <div className="sidebar-resize-handle" onMouseDown={startResize} />

      {/* Portal menü — document.body'e render edilir, stacking context dışında */}
      {openMenu && createPortal(
        <div
          ref={menuRef}
          className="session-menu"
          style={{ top: openMenu.pos.top, left: openMenu.pos.left }}
        >
          <button className="session-menu-item danger" type="button" onClick={() => { onDeleteSession(openMenu.id); setOpenMenu(null); }}>
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v6M14 11v6"/><path d="M9 6V4h6v2"/>
            </svg>
            {en ? "Delete chat" : "Sohbeti sil"}
          </button>
        </div>,
        document.body
      )}

      {settingsPos && createPortal(
        <div
          ref={settingsRef}
          className="session-menu settings-popup"
          style={{ top: settingsPos.top, left: settingsPos.left, transform: "translateY(-100%)" }}
        >
          <div className="settings-popup-item">
            <span className="settings-popup-label">{en ? "Language" : "Dil"}</span>
            <select
              className="settings-select"
              value={language}
              onChange={(e) => void handleLanguageChange(e.target.value as "tr" | "en")}
              disabled={languageSaving}
            >
              <option value="tr">Türkçe</option><option value="en">English</option>
            </select>
          </div>
          <div className="settings-popup-item">
            <span className="settings-popup-label">{en ? "Notifications" : "Bildirimler"}</span>
            <button className={`settings-toggle ${notifications ? "on" : ""}`} onClick={() => setNotifications(!notifications)} type="button">
              <span className="toggle-knob" />
            </button>
          </div>
          <div className="settings-popup-item">
            <span className="settings-popup-label">{en ? "Compact Mode" : "Kompakt Mod"}</span>
            <button className={`settings-toggle ${compact ? "on" : ""}`} onClick={() => setCompact(!compact)} type="button">
              <span className="toggle-knob" />
            </button>
          </div>
          <div className="session-menu-divider" />
          <button className="session-menu-item" type="button" onClick={() => { setSettingsPos(null); setShowSupport(true); }}>
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 015.83 1c0 2-3 3-3 3"/><line x1="12" y1="17" x2="12.01" y2="17"/>
            </svg>
            {en ? "Support" : "Destek"}
          </button>
          <button className="session-menu-item danger" type="button" onClick={() => { setSettingsPos(null); onLogout(); }}>
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4"/>
              <polyline points="16 17 21 12 16 7"/>
              <line x1="21" y1="12" x2="9" y2="12"/>
            </svg>
            {en ? "Log Out" : "Çıkış Yap"}
          </button>
        </div>,
        document.body
      )}

      {showSupport && createPortal(
        <div className="support-backdrop" onClick={() => setShowSupport(false)}>
          <div className="support-panel" onClick={(e) => e.stopPropagation()}>
            <div className="support-header">
              <span className="support-title">Destek</span>
              <button className="settings-close" onClick={() => setShowSupport(false)} type="button">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
                </svg>
              </button>
            </div>
            <div className="support-body">
              <div className="support-section-label">{en ? "FAQ" : "Sık Sorulan Sorular"}</div>
              <div className="support-faq-item">
                <div className="support-faq-q">{en ? "How do I book an appointment?" : "Randevu nasıl alırım?"}</div>
                <div className="support-faq-a">{en ? "Ask the AI assistant in chat to book an appointment." : "Sohbet penceresine \"randevu almak istiyorum\" yazarak yapay zeka asistanından yardım isteyebilirsiniz."}</div>
              </div>
              <div className="support-faq-item">
                <div className="support-faq-q">{en ? "How do I end my session?" : "Oturumumu nasıl sonlandırırım?"}</div>
                <div className="support-faq-a">{en ? "Use the Settings menu in the lower-left corner and choose Log Out." : "Sol alt köşedeki Ayarlar menüsünden \"Çıkış Yap\" seçeneğine tıklayabilirsiniz."}</div>
              </div>
              <div className="support-faq-item">
                <div className="support-faq-q">{en ? "How do I access past chats?" : "Geçmiş sohbetlere nasıl erişirim?"}</div>
                <div className="support-faq-a">{en ? "Choose a previous chat from the Sessions list in the left panel." : "Sol paneldeki SESSIONS listesinden daha önceki sohbetlerinize tıklayarak erişebilirsiniz."}</div>
              </div>
              <div className="support-section-label" style={{ marginTop: 20 }}>{en ? "Contact" : "İletişim"}</div>
              <div className="support-contact-item">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/>
                </svg>
                <span>destek@cognivault.local</span>
              </div>
              <div className="support-contact-item">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M22 16.92v3a2 2 0 01-2.18 2 19.79 19.79 0 01-8.63-3.07A19.5 19.5 0 013.07 9.81a19.79 19.79 0 01-3.07-8.68A2 2 0 012 .18h3a2 2 0 012 1.72c.127.96.361 1.903.7 2.81a2 2 0 01-.45 2.11L6.09 7.91a16 16 0 006 6l1.27-1.27a2 2 0 012.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0122 16.92z"/>
                </svg>
                <span>+90 (212) 555 00 00</span>
              </div>
              <div className="support-version">v1.0.0-mvp · Cognivault AI</div>
            </div>
          </div>
        </div>,
        document.body
      )}

      {showMainMenu && createPortal(
        <div className="main-menu-backdrop" onClick={() => setShowMainMenu(false)}>
          <aside className="main-menu-panel" onClick={(e) => e.stopPropagation()}>
            <div className="main-menu-header">
              <div>
                <span className="main-menu-kicker">Menu</span>
                <h3>{en ? "My Account" : "Hesabım"}</h3>
              </div>
              <button className="settings-close" onClick={() => setShowMainMenu(false)} type="button" aria-label={en ? "Close menu" : "Menüyü kapat"}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
                </svg>
              </button>
            </div>

            <div className="main-menu-account">
              <div className="main-menu-avatar">{initials}</div>
              <div className="main-menu-account-info">
                <strong>{user.full_name}</strong>
                <span>{user.email}</span>
                <div className="main-menu-badges">
                  <span className={`role-badge ${roleName}`}>{roleName}</span>
                  <span>{user.locale.toUpperCase()}</span>
                </div>
              </div>
            </div>

            <div className="main-menu-section">
              <div className="main-menu-label">Workspace</div>
              <button
                className="main-menu-item"
                type="button"
                onClick={() => { setShowMainMenu(false); isEnterpriseUser ? onViewEnterprise() : onNewSession(); }}
              >
                <span>{isEnterpriseUser ? (en ? "Open enterprise intake" : "Kurumsal intake aç") : (en ? "Start new chat" : "Yeni sohbet başlat")}</span>
                <small>{isEnterpriseUser ? (en ? "Route customer requests into ticket and handoff flow" : "Müşteri talebini ticket/routing akışına al") : (en ? "Open a clean AI session" : "Temiz bir AI oturumu aç")}</small>
              </button>
              {user.role.name === "customer" && (
                <button
                  className="main-menu-item"
                  type="button"
                  onClick={() => { setShowMainMenu(false); onViewAppointments(); }}
                >
                  <span>{en ? "My Appointments" : "Randevularım"}</span>
                  <small>{en ? "View active and past appointments" : "Aktif ve geçmiş randevuları gör"}</small>
                </button>
              )}
              {(user.role.name === "operator" || user.role.name === "admin") && (
                <button
                  className="main-menu-item"
                  type="button"
                  onClick={() => { setShowMainMenu(false); onViewEnterprise(); }}
                >
                  <span>Enterprise Panel</span>
                  <small>{en ? "Ticket, routing and handoff workspace" : "Ticket, routing ve handoff ekranı"}</small>
                </button>
              )}
            </div>

            {user.role.name === "operator" && (
              <div className="main-menu-section">
                <div className="main-menu-label">{en ? "Operator Panel" : "Operatör Paneli"}</div>
                <div className="main-menu-operator-summary">
                  <div className="main-menu-op-stat">
                    <strong>{operatorActiveAppointments.length}</strong>
                    <span>{en ? "Active" : "Aktif"}</span>
                  </div>
                  <div className="main-menu-op-stat">
                    <strong>{operatorUpcomingAppointments.length}</strong>
                    <span>{en ? "Upcoming" : "Yaklaşan"}</span>
                  </div>
                  <div className="main-menu-op-stat">
                    <strong>{appointments.length}</strong>
                    <span>{en ? "Total" : "Toplam"}</span>
                  </div>
                </div>

                {operatorMenuAppointments.length === 0 ? (
                  <div className="main-menu-op-empty">{en ? "No active appointments to track right now." : "Şu anda takip edilecek aktif randevu yok."}</div>
                ) : (
                  <div className="main-menu-op-list">
                    {operatorMenuAppointments.map((appointment) => {
                      const appointmentDate = safeAppointmentDate(appointment.scheduled_at);
                      const active = isActiveAppointment(appointment);
                      return (
                        <div className={`main-menu-op-item ${active ? "main-menu-op-item--active" : ""}`} key={appointment.id}>
                          <div className="main-menu-op-row">
                            <strong>{appointment.user_name ?? (en ? "Customer" : "Müşteri")}</strong>
                            <span>{statusLabel(appointment.status)}</span>
                          </div>
                          <div className="main-menu-op-dept">{appointment.department}</div>
                          <div className="main-menu-op-meta">
                            <span>{appointment.confirmation_code}</span>
                            <span>{appointmentDate ? menuDateTime.format(appointmentDate) : (en ? "No date" : "Tarih yok")}</span>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            )}

            <div className="main-menu-section">
              <div className="main-menu-label">{en ? "Preferences" : "Tercihler"}</div>
              <label className="main-menu-control">
                <span>{en ? "Language" : "Dil"}</span>
                <select
                  className="settings-select"
                  value={language}
                  onChange={(e) => void handleLanguageChange(e.target.value as "tr" | "en")}
                  disabled={languageSaving}
                >
                  <option value="tr">Türkçe</option>
                  <option value="en">English</option>
                </select>
              </label>
              <label className="main-menu-control">
                <span>{en ? "Notifications" : "Bildirimler"}</span>
                <button className={`settings-toggle ${notifications ? "on" : ""}`} onClick={() => setNotifications(!notifications)} type="button">
                  <span className="toggle-knob" />
                </button>
              </label>
              <label className="main-menu-control">
                <span>{en ? "Compact mode" : "Kompakt mod"}</span>
                <button className={`settings-toggle ${compact ? "on" : ""}`} onClick={() => setCompact(!compact)} type="button">
                  <span className="toggle-knob" />
                </button>
              </label>
            </div>

            <div className="main-menu-section">
              <div className="main-menu-label">{en ? "Help and security" : "Yardım ve güvenlik"}</div>
              <button
                className="main-menu-item"
                type="button"
                onClick={() => { setShowMainMenu(false); setShowSupport(true); }}
              >
                <span>{en ? "Support center" : "Destek merkezi"}</span>
                <small>{en ? "FAQ and contact information" : "SSS ve iletişim bilgileri"}</small>
              </button>
              <div className="main-menu-note">
                {en ? "Session, role permissions and actions are tracked through the audit trail." : "Oturum, rol bazlı yetkiler ve aksiyon kayıtları audit trail üzerinden takip edilir."}
              </div>
            </div>

            <button
              className="main-menu-logout"
              type="button"
              onClick={() => { setShowMainMenu(false); onLogout(); }}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4"/>
                <polyline points="16 17 21 12 16 7"/>
                <line x1="21" y1="12" x2="9" y2="12"/>
              </svg>
              {en ? "Log out" : "Hesaptan çıkış yap"}
            </button>
          </aside>
        </div>,
        document.body
      )}
    </aside>
  );
}
