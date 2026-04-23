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
export type AppointmentInMessage = {
  confirmation_code: string;
  department: string;
  scheduled_at: string;
  location: string;
  purpose?: string | null;
  status: string;
};
export type ChatMessage = {
  id: number;
  sender: "user" | "assistant" | "system" | "tool";
  content: string;
  language: string;
  metadata_json?: Record<string, unknown> | null;
  created_at: string;
  appointment?: AppointmentInMessage | null;
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
  created_at: string;
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
  user_name?: string | null;
  user_id?: number | null;
};

export type Organization = {
  id: number;
  name: string;
  domain?: string | null;
};
export type EnterpriseDepartment = {
  id: number;
  organization_id: number;
  name: string;
  description?: string | null;
  is_active: boolean;
};
export type EnterpriseCustomer = {
  id: number;
  organization_id: number;
  full_name: string;
  email?: string | null;
  phone?: string | null;
  external_ref?: string | null;
};
export type EnterpriseTicket = {
  id: number;
  session_id?: number | null;
  customer: EnterpriseCustomer;
  department?: EnterpriseDepartment | null;
  intent: string;
  description: string;
  status: string;
  priority: string;
  confidence: number;
  handoff_package?: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
};
export type EnterpriseSessionSummary = {
  id: number;
  chat_session_id: number;
  customer: EnterpriseCustomer;
  department?: EnterpriseDepartment | null;
  status: string;
  intent?: string | null;
  confidence: number;
  last_message_preview?: string | null;
  created_at: string;
  updated_at: string;
};
export type EnterpriseSessionDetail = EnterpriseSessionSummary & {
  messages: ChatMessage[];
  handoff_package?: Record<string, unknown> | null;
};
export type EnterpriseMetrics = {
  organization: Organization;
  total_tickets: number;
  active_sessions: number;
  escalations: number;
  appointments: number;
};
export type EnterpriseOverview = {
  metrics: EnterpriseMetrics;
  departments: EnterpriseDepartment[];
  tickets: EnterpriseTicket[];
  sessions: EnterpriseSessionSummary[];
};
export type EnterpriseDecision = {
  intent: string;
  department?: EnterpriseDepartment | null;
  confidence: number;
  action: string;
  ticket?: EnterpriseTicket | null;
  appointment?: Appointment | null;
  handoff_package?: Record<string, unknown> | null;
  explanation: string;
};
export type EnterpriseMessageResponse = {
  session: EnterpriseSessionDetail;
  assistant_message: string;
  decision: EnterpriseDecision;
};
