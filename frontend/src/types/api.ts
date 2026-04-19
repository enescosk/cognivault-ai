export type Role = {
  id: number;
  name: string;
  description: string;
};

export type User = {
  id: number;
  full_name: string;
  email: string;
  locale: string;
  department?: string | null;
  title?: string | null;
  is_active: boolean;
  role: Role;
};

export type AuthResponse = {
  access_token: string;
  token_type: string;
  user: User;
};

export type ChatSessionSummary = {
  id: number;
  title: string;
  status: string;
  created_at: string;
  updated_at: string;
  last_message_preview?: string | null;
};

export type ChatMessage = {
  id: number;
  sender: "user" | "assistant" | "system" | "tool";
  content: string;
  language: string;
  metadata_json?: Record<string, unknown> | null;
  created_at: string;
};

export type ChatSessionDetail = {
  id: number;
  title: string;
  status: string;
  workflow_state: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  messages: ChatMessage[];
};

export type AgentReply = {
  message: string;
  language: string;
  outcome: string;
  confirmation_card?: ConfirmationCard | null;
};

export type SendMessageResponse = {
  session: ChatSessionDetail;
  assistant_reply: AgentReply;
};

export type ConfirmationCard = {
  type: "appointment_confirmation";
  confirmation_code: string;
  department: string;
  scheduled_at: string;
  location: string;
  contact_phone: string;
  status: string;
};

export type AuditLog = {
  id: number;
  timestamp: string;
  user_id?: number | null;
  session_id?: number | null;
  action_type: string;
  tool_name?: string | null;
  result_status: string;
  success: boolean;
  explanation: string;
  details?: Record<string, unknown> | null;
};

export type Metrics = {
  active_sessions: number;
  confirmed_appointments: number;
  audit_events_today: number;
  completion_rate: number;
};

export type Appointment = {
  id: number;
  confirmation_code: string;
  department: string;
  purpose: string;
  contact_phone: string;
  notes?: string | null;
  language: string;
  status: string;
  scheduled_at: string;
  location: string;
  created_at: string;
};
