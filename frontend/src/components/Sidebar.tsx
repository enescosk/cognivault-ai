import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { ChatSessionSummary, User } from "../types/api";

type SidebarProps = {
  user: User;
  sessions: ChatSessionSummary[];
  selectedSessionId?: number;
  onSelectSession: (sessionId: number) => void;
  onNewSession: () => void;
  onDeleteSession: (sessionId: number) => void;
  onLogout: () => void;
};

type MenuPos = { top: number; left: number };

export function Sidebar({ user, sessions, selectedSessionId, onSelectSession, onNewSession, onDeleteSession, onLogout }: SidebarProps) {
  const initials = user.full_name.split(" ").map((n) => n[0]).join("").toUpperCase().slice(0, 2);
  const roleName = user.role.name.toLowerCase();
  const [language, setLanguage] = useState(user.locale === "tr" ? "Türkçe" : "English");
  const [notifications, setNotifications] = useState(true);
  const [compact, setCompact] = useState(false);
  const [width, setWidth] = useState(280);
  const [hoveredSession, setHoveredSession] = useState<number | null>(null);
  const [openMenu, setOpenMenu] = useState<{ id: number; pos: MenuPos } | null>(null);
  const [settingsPos, setSettingsPos] = useState<MenuPos | null>(null);
  const [showSupport, setShowSupport] = useState(false);
  const resizing = useRef(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const settingsRef = useRef<HTMLDivElement>(null);

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
          <button className="nav-new-btn" onClick={onNewSession} type="button">
            <span>New Session</span>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="12" y1="5" x2="12" y2="19"/>
              <line x1="5" y1="12" x2="19" y2="12"/>
            </svg>
          </button>
          <div className="nav-section-label">Sessions</div>
          {sessions.length === 0 ? (
            <div style={{ padding: "10px 12px", fontSize: "0.82rem", color: "var(--text-3)" }}>No sessions yet</div>
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
                  <span className="session-preview">{session.last_message_preview ?? "No activity yet"}</span>
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
        </nav>

      </div>

      <div className="sidebar-bottom">
        <button className="settings-btn" onClick={handleSettingsClick} type="button">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="3"/>
            <path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z"/>
          </svg>
          Ayarlar
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
          <button className="session-menu-item" type="button" onClick={() => setOpenMenu(null)}>
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/>
              <line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/>
            </svg>
            Paylaş
          </button>
          <button className="session-menu-item" type="button" onClick={() => setOpenMenu(null)}>
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 013 3L7 19l-4 1 1-4L16.5 3.5z"/>
            </svg>
            Yeniden adlandır
          </button>
          <button className="session-menu-item session-menu-item--arrow" type="button" onClick={() => setOpenMenu(null)}>
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z"/>
            </svg>
            <span>Projeye taşı</span>
            <svg className="session-menu-chevron" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="9 18 15 12 9 6"/>
            </svg>
          </button>
          <div className="session-menu-divider" />
          <button className="session-menu-item" type="button" onClick={() => setOpenMenu(null)}>
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="12" y1="17" x2="12" y2="22"/><path d="M5 17H4a2 2 0 01-2-2V5a2 2 0 012-2h16a2 2 0 012 2v10a2 2 0 01-2 2h-1"/>
              <polygon points="12 15 17 21 7 21"/>
            </svg>
            Sohbeti sabitle
          </button>
          <button className="session-menu-item" type="button" onClick={() => setOpenMenu(null)}>
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="21 8 21 21 3 21 3 8"/><rect x="1" y="3" width="22" height="5"/>
            </svg>
            Arşivle
          </button>
          <div className="session-menu-divider" />
          <button className="session-menu-item danger" type="button" onClick={() => { onDeleteSession(openMenu.id); setOpenMenu(null); }}>
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v6M14 11v6"/><path d="M9 6V4h6v2"/>
            </svg>
            Sil
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
            <span className="settings-popup-label">Dil</span>
            <select className="settings-select" value={language} onChange={(e) => setLanguage(e.target.value)}>
              <option>Türkçe</option><option>English</option>
            </select>
          </div>
          <div className="settings-popup-item">
            <span className="settings-popup-label">Bildirimler</span>
            <button className={`settings-toggle ${notifications ? "on" : ""}`} onClick={() => setNotifications(!notifications)} type="button">
              <span className="toggle-knob" />
            </button>
          </div>
          <div className="settings-popup-item">
            <span className="settings-popup-label">Kompakt Mod</span>
            <button className={`settings-toggle ${compact ? "on" : ""}`} onClick={() => setCompact(!compact)} type="button">
              <span className="toggle-knob" />
            </button>
          </div>
          <div className="session-menu-divider" />
          <button className="session-menu-item" type="button" onClick={() => { setSettingsPos(null); setShowSupport(true); }}>
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 015.83 1c0 2-3 3-3 3"/><line x1="12" y1="17" x2="12.01" y2="17"/>
            </svg>
            Destek
          </button>
          <button className="session-menu-item danger" type="button" onClick={() => { setSettingsPos(null); onLogout(); }}>
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4"/>
              <polyline points="16 17 21 12 16 7"/>
              <line x1="21" y1="12" x2="9" y2="12"/>
            </svg>
            Çıkış Yap
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
              <div className="support-section-label">Sık Sorulan Sorular</div>
              <div className="support-faq-item">
                <div className="support-faq-q">Randevu nasıl alırım?</div>
                <div className="support-faq-a">Sohbet penceresine "randevu almak istiyorum" yazarak yapay zeka asistanından yardım isteyebilirsiniz.</div>
              </div>
              <div className="support-faq-item">
                <div className="support-faq-q">Oturumumu nasıl sonlandırırım?</div>
                <div className="support-faq-a">Sol alt köşedeki Ayarlar menüsünden "Çıkış Yap" seçeneğine tıklayabilirsiniz.</div>
              </div>
              <div className="support-faq-item">
                <div className="support-faq-q">Geçmiş sohbetlere nasıl erişirim?</div>
                <div className="support-faq-a">Sol paneldeki SESSIONS listesinden daha önceki sohbetlerinize tıklayarak erişebilirsiniz.</div>
              </div>
              <div className="support-section-label" style={{ marginTop: 20 }}>İletişim</div>
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
    </aside>
  );
}
