export type RoleName = "customer" | "operator" | "admin";

export type Role = {
  id: number;
  name: RoleName | string;
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
export type IntelligenceActivityEvent = {
  label: string;
  status: "completed" | "in_progress" | "pending" | "blocked" | string;
};
export type IntelligenceActivity = {
  type: "external_outreach";
  job_id: number;
  company: string;
  address?: string | null;
  phone?: string | null;
  email?: string | null;
  source_url?: string | null;
  source_kind?: string | null;
  source_label?: string | null;
  confidence: number;
  status: string;
  failure_reason?: string | null;
  extracted_terms?: {
    company?: string;
    location?: string | null;
    purpose?: string | null;
    search_query?: string;
    entity_type?: "company" | "category" | string;
  };
  events: IntelligenceActivityEvent[];
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

export type ClinicalPatient = {
  id: number;
  clinic_id: number;
  full_name?: string | null;
  phone: string;
  language: string;
  source: string;
  created_at: string;
  updated_at: string;
};
export type ClinicalMessage = {
  id: number;
  conversation_id: number;
  sender: "patient" | "assistant" | "operator" | "system";
  content: string;
  language: string;
  intent?: string | null;
  confidence_score?: number | null;
  external_message_id?: string | null;
  metadata_json?: Record<string, unknown> | null;
  created_at: string;
};
export type ClinicalConversationSummary = {
  id: number;
  clinic_id: number;
  patient: ClinicalPatient;
  channel: string;
  status: string;
  language: string;
  intent?: string | null;
  confidence_score?: number | null;
  persona_name?: string | null;
  doctor_inbox: boolean;
  last_message_preview?: string | null;
  created_at: string;
  updated_at: string;
};
export type ClinicalConversationDetail = ClinicalConversationSummary & {
  messages: ClinicalMessage[];
};
export type ShadowReview = {
  id: number;
  clinic_id: number;
  conversation_id: number;
  patient_message_id: number;
  draft_reply: string;
  intent: string;
  confidence_score: number;
  risk_reason: string;
  status: string;
  persona_name?: string | null;
  channel?: string | null;
  final_reply?: string | null;
  metadata_json?: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
};
export type ClinicalMetrics = {
  clinic_name: string;
  conversations_today: number;
  total_conversations: number;
  pending_shadow_reviews: number;
  doctor_inbox_count: number;
  phone_calls_today: number;
  auto_reply_rate: number;
  appointments_pending: number;
  reminders_due: number;
  frustration_events: number;
};
export type ClinicalOverview = {
  metrics: ClinicalMetrics;
  conversations: ClinicalConversationSummary[];
  doctor_inbox: ClinicalConversationSummary[];
  shadow_reviews: ShadowReview[];
};
export type ClinicalComplianceProfile = {
  clinic_id: number;
  clinic_name: string;
  data_residency_default: string;
  external_transfer_allowed: boolean;
  processor_inventory: Array<Record<string, unknown>>;
  production_modes: Array<Record<string, unknown>>;
  mandatory_controls: string[];
  blocked_by_default: string[];
  operator_review_triggers: string[];
};
export type ClinicalPatentDossier = {
  working_title: string;
  technical_field: string;
  problem: string;
  solution_summary: string;
  candidate_independent_claims: string[];
  candidate_dependent_claims: string[];
  figures_to_prepare: string[];
  evidence_to_preserve: string[];
  next_actions: string[];
};
export type ClinicalSlotAppointment = {
  id: string;
  time: string;
  patient_name: string;
  doctor: string;
  branch: string;
  department: string;
  date_label: string;
  phone: string;
  status: "confirmed" | "pending" | string;
  status_label: string;
};
export type ClinicalAppointmentRow = {
  id: number;
  patient_id: number;
  patient_name: string | null;
  patient_phone: string | null;
  conversation_id: number | null;
  department: string;
  physician_name: string | null;
  branch_name: string | null;
  starts_at: string | null;
  status: "pending" | "confirmed" | "cancelled" | string;
  notes: string | null;
  created_at: string;
};
export type ClinicalSlotItem = {
  id: string;
  department: string;
  doctor: string;
  date_label: string;
  time_range: string;
  capacity: number;
  booked: number;
  open: number;
  status: "available" | "limited" | "full" | string;
  next_available: string;
  waitlist_count: number;
  appointments?: ClinicalSlotAppointment[];
};
export type ClinicalSlotBoard = {
  summary: {
    clinic_mode: string;
    occupancy_rate: number;
    full_departments: number;
    next_open_slot: string;
    waitlist_total: number;
  };
  schedule: ClinicalSlotItem[];
  acceptance_rules: Array<{ rule: string; result: string }>;
  test_scenarios: Array<{ label: string; message: string; expected_action: string; expected_result: string }>;
};
export type WebhookIngestionResponse = {
  ok: boolean;
  clinic_id: number;
  patient_id: number;
  conversation_id: number;
  message_id: number;
  action: string;
  reply?: string | null;
  shadow_review_id?: number | null;
  // AI triage outputs (playground UI için ek alanlar — backend bunları
  // ingestion_payload'a opsiyonel olarak ekliyor)
  intent?: string | null;
  confidence?: number | null;
  risk?: "low" | "medium" | "high" | null;
  requires_human_review?: boolean;
  persona_name?: string | null;
  risk_reason?: string | null;
};
export type ClinicalPersona = {
  id: "selin" | "arzu" | "can";
  display_name: string;
  role: string;
  voice: string;
  tone: string;
  specialty: string;
  safety_rule: string;
};
export type ClinicalAppointment = {
  id: number;
  clinic_id: number;
  patient_id: number;
  conversation_id?: number | null;
  department: string;
  starts_at?: string | null;
  status: string;
  notes?: string | null;
  metadata_json?: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
};
