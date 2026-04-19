import { useEffect, useRef, useState } from "react";

import type { ChatMessage, ChatSessionDetail, User } from "../types/api";

type ChatWindowProps = {
  session: ChatSessionDetail | null;
  user: User;
  sending: boolean;
  onSend: (content: string) => Promise<void>;
};

const formatter = new Intl.DateTimeFormat("en-GB", {
  dateStyle: "medium",
  timeStyle: "short"
});

type ConfirmationMetadata = {
  type: "appointment_confirmation";
  confirmation_code: string;
  department: string;
  scheduled_at: string;
  location: string;
  contact_phone: string;
  status: string;
};

function ConfirmationCard({ message }: { message: ChatMessage }) {
  const metadata = message.metadata_json as ConfirmationMetadata | null | undefined;
  if (!metadata || metadata.type !== "appointment_confirmation") {
    return null;
  }

  return (
    <div className="confirmation-card">
      <div className="confirmation-header">
        <span className="status-badge success">Confirmed</span>
        <strong>{String(metadata.confirmation_code)}</strong>
      </div>
      <div className="confirmation-grid">
        <div>
          <span>Department</span>
          <strong>{String(metadata.department)}</strong>
        </div>
        <div>
          <span>When</span>
          <strong>{formatter.format(new Date(String(metadata.scheduled_at)))}</strong>
        </div>
        <div>
          <span>Location</span>
          <strong>{String(metadata.location)}</strong>
        </div>
        <div>
          <span>Phone</span>
          <strong>{String(metadata.contact_phone)}</strong>
        </div>
      </div>
    </div>
  );
}

export function ChatWindow({ session, user, sending, onSend }: ChatWindowProps) {
  const [draft, setDraft] = useState("");
  const scrollRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [session?.messages]);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!draft.trim() || sending) {
      return;
    }
    const content = draft;
    setDraft("");
    await onSend(content);
  }

  return (
    <section className="chat-panel">
      <div className="chat-header">
        <div>
          <div className="eyebrow">Agent Workspace</div>
          <h2>{session?.title ?? "Loading session..."}</h2>
        </div>
        <div className="role-pill light">
          {user.role.name} · {user.locale.toUpperCase()}
        </div>
      </div>

      <div className="message-stream" ref={scrollRef}>
        {session?.messages.map((message) => (
          <div
            className={`message-row ${message.sender === "user" ? "outbound" : "inbound"}`}
            key={message.id}
          >
            <div className="message-bubble">
              <div className="message-meta">
                <strong>{message.sender === "user" ? "You" : "Cognivault AI"}</strong>
                <span>{formatter.format(new Date(message.created_at))}</span>
              </div>
              <p>{message.content}</p>
              <ConfirmationCard message={message} />
            </div>
          </div>
        ))}
        {session?.messages.length === 0 ? (
          <div className="empty-state">
            Start in Turkish or English. Try:
            <code>Teknik destek için randevu almak istiyorum.</code>
            <code>I need a billing appointment for tomorrow.</code>
          </div>
        ) : null}
      </div>

      <form className="composer" onSubmit={handleSubmit}>
        <textarea
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="Ask in Turkish or English. The agent will guide the workflow step by step."
          rows={3}
        />
        <button className="primary-button" disabled={sending || !draft.trim()} type="submit">
          {sending ? "Processing..." : "Send"}
        </button>
      </form>
    </section>
  );
}
