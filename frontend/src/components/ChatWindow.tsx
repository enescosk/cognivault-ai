import { useEffect, useRef, useState } from "react";
import type { ChatSessionDetail, User } from "../types/api";

type ChatWindowProps = {
  session: ChatSessionDetail | null;
  user: User;
  sending: boolean;
  pendingMessage: string | null;
  onSend: (content: string) => void;
};

const trDateTime = new Intl.DateTimeFormat("tr-TR", { dateStyle: "short", timeStyle: "short" });

export function ChatWindow({ session, user, sending, pendingMessage, onSend }: ChatWindowProps) {
  const [input, setInput] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [session?.messages, sending]);

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  }

  function handleSubmit() {
    const trimmed = input.trim();
    if (!trimmed || sending) return;
    setInput("");
    onSend(trimmed);
  }

  const roleName = user.role.name;
  const locale = user.locale.toUpperCase();

  const messages = session?.messages ?? [];

  return (
    <div className="chat-panel">
      <div className="chat-header">
        <div className="chat-header-left">
          <div className="chat-title">{session?.title ?? "Agent Workspace"}</div>
          <div className="chat-subtitle">Guided enterprise workflow · RBAC enforced</div>
        </div>
        <div className="chat-badges">
          <span className="chat-badge">
            <svg width="8" height="8" viewBox="0 0 24 24" fill="currentColor"><circle cx="12" cy="12" r="12"/></svg>
            {roleName} · {locale}
          </span>
          <span className="chat-badge">
            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
              <path d="M7 11V7a5 5 0 0110 0v4"/>
            </svg>
            Audited
          </span>
        </div>
      </div>

      <div className="message-stream">
        {/* Boş alan — mesajları aşağı iter */}
        <div className="message-stream-spacer" />

        {messages.length === 0 && !sending ? (
          <div className="empty-state">
            <div className="empty-icon">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/>
              </svg>
            </div>
            <h4>Start a conversation</h4>
            <p>Ask in Turkish or English. The agent will guide the workflow step by step.</p>
          </div>
        ) : (
          messages.map((msg) => {
            const isUser = msg.sender === "user";
            if (msg.sender === "system" || msg.sender === "tool") return null;
            return (
              <div key={msg.id} className={`message-row ${isUser ? "outbound" : ""}`}>
                {/* AI avatarı — sadece AI mesajlarında sol tarafta */}
                {!isUser && (
                  <div className="msg-avatar">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M12 2a4 4 0 014 4v2a4 4 0 01-8 0V6a4 4 0 014-4z"/><path d="M3 20c0-4 4-7 9-7s9 3 9 7"/>
                    </svg>
                  </div>
                )}
                <div className="message-bubble">
                  <div className="message-meta">
                    {/* Kullanıcıda önce saat, sonra isim (sağ hizalı meta) */}
                    {isUser && <span className="message-time">{trDateTime.format(new Date(msg.created_at))}</span>}
                    <span className="message-sender">{isUser ? user.full_name : "Cognivault AI"}</span>
                    {!isUser && <span className="message-time">{trDateTime.format(new Date(msg.created_at))}</span>}
                  </div>
                  <div className="message-content">{msg.content}</div>
                  {msg.appointment && (
                    <div className="confirmation-card">
                      <div className="confirmation-header">
                        <span className="confirmation-label">Randevu Onaylandı</span>
                        <span className="status-badge success">Onaylı</span>
                      </div>
                      <div className="confirmation-grid">
                        <div>
                          <span className="cf-label">Departman</span>
                          <span className="cf-value">{msg.appointment.department}</span>
                        </div>
                        <div>
                          <span className="cf-label">Kod</span>
                          <span className="cf-value" style={{ fontFamily: "var(--font-mono)", color: "var(--green)" }}>
                            {msg.appointment.confirmation_code}
                          </span>
                        </div>
                        <div>
                          <span className="cf-label">Tarih</span>
                          <span className="cf-value">{trDateTime.format(new Date(msg.appointment.scheduled_at))}</span>
                        </div>
                        <div>
                          <span className="cf-label">Amaç</span>
                          <span className="cf-value">{msg.appointment.purpose ?? "—"}</span>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            );
          })
        )}

        {/* Gönderilen mesaj — API yanıt vermeden önce hemen göster */}
        {sending && pendingMessage && (
          <div className="message-row outbound">
            <div className="message-bubble">
              <div className="message-meta">
                <span className="message-time">şimdi</span>
                <span className="message-sender">{user.full_name}</span>
              </div>
              <div className="message-content">{pendingMessage}</div>
            </div>
          </div>
        )}

        {/* AI düşünüyor */}
        {sending && (
          <div className="message-row">
            <div className="msg-avatar">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 2a4 4 0 014 4v2a4 4 0 01-8 0V6a4 4 0 014-4z"/><path d="M3 20c0-4 4-7 9-7s9 3 9 7"/>
              </svg>
            </div>
            <div className="message-bubble">
              <div className="message-meta">
                <span className="message-sender">Cognivault AI</span>
              </div>
              <div className="typing-indicator">
                <span className="typing-dot" />
                <span className="typing-dot" />
                <span className="typing-dot" />
              </div>
            </div>
          </div>
        )}

        {/* Scroll anchor */}
        <div ref={bottomRef} />
      </div>

      <div className="composer-area">
        <div className="composer-box">
          <textarea
            className="composer-textarea"
            placeholder="Türkçe veya İngilizce yazın. Enter ile gönderin, Shift+Enter yeni satır."
            value={input}
            rows={1}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={sending}
          />
          <button className="send-btn" onClick={handleSubmit} disabled={sending || !input.trim()} type="button" aria-label="Send">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <line x1="22" y1="2" x2="11" y2="13"/>
              <polygon points="22 2 15 22 11 13 2 9 22 2"/>
            </svg>
          </button>
        </div>
        <div className="composer-hint">Enter ile gönder · Shift+Enter yeni satır · Tüm işlemler kayıt altında</div>
      </div>
    </div>
  );
}
