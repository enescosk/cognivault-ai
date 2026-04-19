import type { ChatSessionSummary, User } from "../types/api";

type SidebarProps = {
  user: User;
  sessions: ChatSessionSummary[];
  selectedSessionId?: number;
  onSelectSession: (sessionId: number) => void;
  onNewSession: () => void;
  onLogout: () => void;
};

export function Sidebar({
  user,
  sessions,
  selectedSessionId,
  onSelectSession,
  onNewSession,
  onLogout
}: SidebarProps) {
  return (
    <aside className="sidebar">
      <div className="sidebar-card profile-card">
        <div className="brand-chip subtle">Identity</div>
        <h2>{user.full_name}</h2>
        <div className="role-pill">{user.role.name}</div>
        <p>{user.email}</p>
        <div className="profile-meta">
          <span>{user.department ?? "Enterprise User"}</span>
          <span>{user.locale.toUpperCase()}</span>
        </div>
        <button className="secondary-button" onClick={onLogout} type="button">
          Sign out
        </button>
      </div>

      <div className="sidebar-card">
        <div className="sidebar-section-header">
          <div>
            <div className="eyebrow">Conversations</div>
            <h3>Workflow Sessions</h3>
          </div>
          <button className="ghost-button" onClick={onNewSession} type="button">
            New
          </button>
        </div>
        <div className="conversation-list">
          {sessions.map((session) => (
            <button
              key={session.id}
              className={`conversation-item ${selectedSessionId === session.id ? "active" : ""}`}
              onClick={() => onSelectSession(session.id)}
              type="button"
            >
              <strong>{session.title}</strong>
              <span>{session.last_message_preview ?? "No activity yet"}</span>
            </button>
          ))}
        </div>
      </div>
    </aside>
  );
}
